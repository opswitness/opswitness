use anyhow::{bail, Context, Result};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs,
    io::Read,
    path::{Component, Path, PathBuf},
};
use walkdir::WalkDir;

#[derive(Debug, Deserialize)]
struct ResourceManifest {
    schema_version: u32,
    target: String,
    files: Vec<ResourceFile>,
}

#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(rename_all = "snake_case")]
enum ResourceKind {
    File,
    Symlink,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ResourceFile {
    path: String,
    kind: ResourceKind,
    sha256: Option<String>,
    size: Option<u64>,
    executable: Option<bool>,
    target: Option<String>,
}

#[derive(Debug, Deserialize)]
struct VendorLock {
    schema_version: u32,
    target: String,
    components: Vec<VendorComponent>,
}

#[derive(Debug, Deserialize)]
struct VendorComponent {
    id: String,
    entrypoints: Vec<String>,
    #[serde(default)]
    required_prefixes: Vec<String>,
}

fn safe_relative(value: &str) -> Result<PathBuf> {
    let path = PathBuf::from(value);
    if path.as_os_str().is_empty()
        || path.is_absolute()
        || path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        bail!("unsafe runtime resource path: {value}");
    }
    Ok(path)
}

fn digest(path: &Path) -> Result<(String, u64)> {
    let mut file = fs::File::open(path)
        .with_context(|| format!("cannot open runtime resource {}", path.display()))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    let mut size = 0_u64;
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
        size += read as u64;
    }
    Ok((hex::encode(hasher.finalize()), size))
}

fn lexical_symlink_destination(relative_link: &Path, target: &Path) -> Result<PathBuf> {
    let mut destination = PathBuf::new();
    let parent = relative_link.parent().unwrap_or_else(|| Path::new(""));
    for component in parent.components().chain(target.components()) {
        match component {
            Component::Normal(part) => destination.push(part),
            Component::CurDir => {}
            Component::ParentDir => {
                if !destination.pop() {
                    bail!("runtime resource symlink target escapes the payload");
                }
            }
            Component::Prefix(_) | Component::RootDir => {
                bail!("runtime resource symlink target must be relative");
            }
        }
    }
    Ok(destination)
}

fn verify_symlink(
    payload_root: &Path,
    relative_link: &Path,
    absolute_link: &Path,
    recorded_target: &str,
) -> Result<()> {
    if recorded_target.is_empty() {
        bail!(
            "runtime resource symlink target is empty: {}",
            relative_link.display()
        );
    }
    let target = Path::new(recorded_target);
    if target.is_absolute() {
        bail!(
            "runtime resource symlink target must be relative: {}",
            relative_link.display()
        );
    }
    let _ = lexical_symlink_destination(relative_link, target)?;
    let actual_target = fs::read_link(absolute_link).with_context(|| {
        format!(
            "cannot read runtime resource symlink {}",
            relative_link.display()
        )
    })?;
    if actual_target != target {
        bail!(
            "runtime resource symlink target mismatch: {}",
            relative_link.display()
        );
    }
    let resolved = fs::canonicalize(
        absolute_link
            .parent()
            .ok_or_else(|| anyhow::anyhow!("runtime resource symlink has no parent"))?
            .join(target),
    )
    .with_context(|| {
        format!(
            "runtime resource symlink target is broken: {}",
            relative_link.display()
        )
    })?;
    if !resolved.starts_with(payload_root) {
        bail!(
            "runtime resource symlink resolves outside the payload: {}",
            relative_link.display()
        );
    }
    Ok(())
}

#[cfg(unix)]
fn is_executable(path: &Path) -> Result<bool> {
    use std::os::unix::fs::PermissionsExt;
    Ok(fs::metadata(path)?.permissions().mode() & 0o111 != 0)
}

pub fn verify_runtime(resource_root: &Path) -> Result<()> {
    let payload = resource_root.join("payload");
    let canonical_payload =
        fs::canonicalize(&payload).context("cannot resolve the runtime payload root")?;
    let manifest_path = payload.join("resource-manifest.json");
    let lock_path = resource_root.join("vendor-lock.json");
    let manifest: ResourceManifest = serde_json::from_slice(
        &fs::read(&manifest_path)
            .with_context(|| format!("missing {}", manifest_path.display()))?,
    )
    .context("invalid resource-manifest.json")?;
    let vendor: VendorLock = serde_json::from_slice(
        &fs::read(&lock_path).with_context(|| format!("missing {}", lock_path.display()))?,
    )
    .context("invalid vendor-lock.json")?;

    if manifest.schema_version != 2 || vendor.schema_version != 1 {
        bail!("unsupported runtime or vendor manifest schema");
    }
    if manifest.target != "aarch64-apple-darwin" || vendor.target != manifest.target {
        bail!("runtime target does not match aarch64-apple-darwin");
    }

    let mut expected = BTreeSet::new();
    for entry in &manifest.files {
        let relative = safe_relative(&entry.path)?;
        if !expected.insert(relative.clone()) {
            bail!("duplicate runtime resource {}", entry.path);
        }
        let absolute = payload.join(&relative);
        let metadata = fs::symlink_metadata(&absolute)
            .with_context(|| format!("missing runtime resource {}", entry.path))?;
        match entry.kind {
            ResourceKind::File => {
                if !metadata.is_file() || metadata.file_type().is_symlink() {
                    bail!("runtime resource is not a regular file: {}", entry.path);
                }
                if entry.target.is_some()
                    || entry.sha256.is_none()
                    || entry.size.is_none()
                    || entry.executable.is_none()
                {
                    bail!(
                        "runtime regular-file manifest entry is incomplete: {}",
                        entry.path
                    );
                }
                let (actual_sha256, actual_size) = digest(&absolute)?;
                if entry.sha256.as_deref() != Some(actual_sha256.as_str())
                    || entry.size != Some(actual_size)
                {
                    bail!("runtime resource integrity failure: {}", entry.path);
                }
                if entry.executable != Some(is_executable(&absolute)?) {
                    bail!("runtime resource mode mismatch: {}", entry.path);
                }
            }
            ResourceKind::Symlink => {
                if !metadata.file_type().is_symlink() {
                    bail!(
                        "runtime resource is not the recorded symlink: {}",
                        entry.path
                    );
                }
                if entry.sha256.is_some() || entry.size.is_some() || entry.executable.is_some() {
                    bail!(
                        "runtime symlink manifest entry has file metadata: {}",
                        entry.path
                    );
                }
                let target = entry.target.as_deref().ok_or_else(|| {
                    anyhow::anyhow!("runtime symlink target is missing: {}", entry.path)
                })?;
                verify_symlink(&canonical_payload, &relative, &absolute, target)?;
            }
        }
    }

    for component in &vendor.components {
        for entrypoint in &component.entrypoints {
            let relative = safe_relative(entrypoint)?;
            if !expected.contains(&relative) {
                bail!(
                    "vendor {} entrypoint is not integrity-locked: {}",
                    component.id,
                    entrypoint
                );
            }
        }
        for prefix in &component.required_prefixes {
            if !expected
                .iter()
                .any(|path| path.to_string_lossy().starts_with(prefix))
            {
                bail!(
                    "vendor {} required resource prefix is empty: {}",
                    component.id,
                    prefix
                );
            }
        }
    }

    let mut actual = BTreeSet::new();
    for entry in WalkDir::new(&payload).follow_links(false) {
        let entry = entry.context("cannot walk the runtime payload")?;
        if entry.file_type().is_dir() {
            continue;
        }
        if !entry.file_type().is_file() && !entry.file_type().is_symlink() {
            bail!(
                "runtime payload contains an unsupported file type: {}",
                entry.path().display()
            );
        }
        let relative = entry
            .path()
            .strip_prefix(&payload)
            .context("runtime payload entry escaped its root")?
            .to_path_buf();
        if relative == Path::new("resource-manifest.json")
            || relative.file_name().is_some_and(|name| name == ".gitkeep")
        {
            continue;
        }
        actual.insert(relative);
    }
    if actual != expected {
        let missing: Vec<_> = expected.difference(&actual).collect();
        let unlisted: Vec<_> = actual.difference(&expected).collect();
        bail!("runtime file inventory mismatch; missing={missing:?}, unlisted={unlisted:?}");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{digest, verify_runtime};
    use serde_json::json;
    use std::{
        fs,
        os::unix::fs::symlink,
        path::{Path, PathBuf},
    };
    use uuid::Uuid;

    struct Fixture {
        root: PathBuf,
        resources: PathBuf,
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.root);
        }
    }

    fn fixture(target: &str, create_link_target: bool) -> Fixture {
        let root = std::env::temp_dir().join(format!(
            "opswitness-runtime-manifest-test-{}",
            Uuid::new_v4()
        ));
        let resources = root.join("runtime");
        let payload = resources.join("payload");
        let target_file = payload.join("node/npm-cli.js");
        fs::create_dir_all(target_file.parent().unwrap()).unwrap();
        fs::write(&target_file, b"console.log('npm');\n").unwrap();
        let link = payload.join("node/npm");
        if create_link_target && target != "npm-cli.js" {
            let requested = link.parent().unwrap().join(target);
            fs::create_dir_all(requested.parent().unwrap()).unwrap();
            fs::write(requested, b"outside\n").unwrap();
        }
        symlink(target, &link).unwrap();
        let (sha256, size) = digest(&target_file).unwrap();
        fs::write(
            payload.join("resource-manifest.json"),
            serde_json::to_vec_pretty(&json!({
                "schema_version": 2,
                "target": "aarch64-apple-darwin",
                "distribution_mode": "adhoc",
                "files": [
                    {
                        "path": "node/npm-cli.js",
                        "kind": "file",
                        "sha256": sha256,
                        "size": size,
                        "executable": false
                    },
                    {
                        "path": "node/npm",
                        "kind": "symlink",
                        "target": target
                    }
                ]
            }))
            .unwrap(),
        )
        .unwrap();
        fs::write(
            resources.join("vendor-lock.json"),
            serde_json::to_vec_pretty(&json!({
                "schema_version": 1,
                "target": "aarch64-apple-darwin",
                "components": [
                    {
                        "id": "node",
                        "entrypoints": ["node/npm-cli.js"],
                        "required_prefixes": ["node/"]
                    }
                ]
            }))
            .unwrap(),
        )
        .unwrap();
        Fixture { root, resources }
    }

    #[test]
    fn accepts_relative_contained_non_broken_symlink() {
        let fixture = fixture("npm-cli.js", false);

        verify_runtime(Path::new(&fixture.resources)).unwrap();
    }

    #[test]
    fn rejects_escaping_and_broken_symlinks() {
        let escaping = fixture("../../outside", true);
        let error = verify_runtime(Path::new(&escaping.resources)).unwrap_err();
        assert!(error.to_string().contains("escapes the payload"));

        let broken = fixture("missing.js", false);
        let error = verify_runtime(Path::new(&broken.resources)).unwrap_err();
        assert!(error.to_string().contains("broken"));
    }
}
