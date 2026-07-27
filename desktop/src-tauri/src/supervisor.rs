use anyhow::{anyhow, bail, Context, Result};
use fs2::FileExt;
use nix::{
    sys::signal::{kill, Signal},
    unistd::Pid,
};
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    ffi::CStr,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    net::{Ipv4Addr, SocketAddrV4, TcpListener},
    os::raw::{c_char, c_int, c_void},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};
use uuid::Uuid;

const PAPERCLIP_HEALTH: &str = "/api/health";
const AIONCORE_HEALTH: &str = "/api/system/info";
const AIONCORE_ASSISTANTS: &str = "/api/assistants";
const AIONCORE_MCP_SERVERS: &str = "/api/mcp/servers";
const AIONCORE_MCP_TEST: &str = "/api/mcp/test-connection";
const BACKEND_HEALTH: &str = "/api/v1/bootstrap";
const BACKEND_DRAIN: &str = "/api/v1/desktop/drain";
const CODEX_ASSISTANT_ID: &str = "bare:8e1acf31";
const OPSWITNESS_MCP_NAME: &str = "OpsWitness (App-managed)";
const OPSWITNESS_MCP_TOOLS: &[&str] = &[
    "qd_fleet_status",
    "qd_runs",
    "qd_run_events",
    "qd_projection_backlog",
    "qd_artifacts",
    "qd_artifact_verify",
    "qd_python_package_status",
    "qd_request_input",
    "qd_watchdog",
    "qd_project_now",
    "qd_workflows",
    "qd_workflow_start",
    "qd_workflow_status",
];
const PAPERCLIP_COMPANY_NAME: &str = "OpsWitness";
const PAPERCLIP_AGENT_NAME: &str = "OpsWitness Service";
const PAPERCLIP_TOKEN_NAME: &str = "opswitness-desktop";

#[derive(Debug, Clone, Serialize)]
pub struct RuntimeStatus {
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

pub trait RuntimeSupervisor: Send {
    fn start(&mut self, status: &mut dyn FnMut(RuntimeStatus)) -> Result<()>;
    fn backend_url(&self) -> Option<&str>;
    fn begin_draining(&self) -> Result<DrainStatus>;
    fn cancel_draining(&self) -> Result<()>;
    fn stop_all(&mut self) -> Result<()>;
}

#[derive(Debug, Clone, Deserialize)]
pub struct DrainStatus {
    pub active_work: bool,
    pub backend_confirmed: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct BackendDrainStatus {
    draining: bool,
    active_work: bool,
    active_work_ids: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ProcessRecord {
    name: String,
    pid: u32,
    executable: PathBuf,
    port: u16,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct InstanceRecord {
    schema_version: u32,
    instance_id: String,
    supervisor_pid: u32,
    resource_root: PathBuf,
    resource_manifest: PathBuf,
    resource_manifest_sha256: String,
    codex_executable: PathBuf,
    processes: Vec<ProcessRecord>,
}

struct OwnedProcess {
    name: &'static str,
    executable: PathBuf,
    port: u16,
    child: Child,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PaperclipCredentials {
    company_id: String,
    agent_id: String,
    api_key: String,
}

pub struct Supervisor {
    resource_payload: PathBuf,
    claude_executable: PathBuf,
    data_root: PathBuf,
    log_root: PathBuf,
    instance_id: String,
    instance_file: PathBuf,
    _instance_lock: File,
    processes: Vec<OwnedProcess>,
    backend_url: Option<String>,
}

impl Supervisor {
    pub fn new(resource_payload: PathBuf, data_root: PathBuf, log_root: PathBuf) -> Result<Self> {
        for directory in [
            &data_root,
            &data_root.join("config"),
            &data_root.join("state"),
            &data_root.join("paperclip"),
            &data_root.join("aion"),
            &data_root.join("runtime-cache"),
            &data_root.join("runtime-cache/tmp"),
            &data_root.join("workspaces"),
            &data_root.join("config/codex"),
            &data_root.join("config/claude"),
            &log_root,
        ] {
            fs::create_dir_all(directory)
                .with_context(|| format!("cannot create {}", directory.display()))?;
            set_private_directory(directory)?;
        }

        let lock_path = data_root.join("runtime-cache/desktop.lock");
        use std::os::unix::fs::OpenOptionsExt;
        if let Ok(metadata) = fs::symlink_metadata(&lock_path) {
            if metadata.file_type().is_symlink() || !metadata.is_file() {
                bail!("desktop single-instance lock is not a regular file");
            }
        }
        let instance_lock = OpenOptions::new()
            .create(true)
            .read(true)
            .write(true)
            .mode(0o600)
            .custom_flags(nix::libc::O_NOFOLLOW)
            .open(&lock_path)
            .with_context(|| format!("cannot open {}", lock_path.display()))?;
        set_private_file(&lock_path)?;
        instance_lock
            .try_lock_exclusive()
            .map_err(|_| anyhow!("another OpsWitness desktop instance is already running"))?;
        let instance_file = data_root.join("runtime-cache/instance.json");
        reconcile_previous_instance(&instance_file, &resource_payload)?;
        let claude_executable = resolve_bundled_claude_executable(&resource_payload)?;

        Ok(Self {
            resource_payload,
            claude_executable,
            data_root: data_root.clone(),
            log_root,
            instance_id: Uuid::new_v4().to_string(),
            instance_file,
            _instance_lock: instance_lock,
            processes: Vec::new(),
            backend_url: None,
        })
    }

    pub fn backend_url(&self) -> Option<&str> {
        self.backend_url.as_deref()
    }

    pub fn start(&mut self, mut status: impl FnMut(RuntimeStatus)) -> Result<()> {
        self.require_disk_space(5 * 1024 * 1024 * 1024)?;

        status(RuntimeStatus {
            message: "Starting the local governance runtime…".into(),
            error: None,
        });
        let paperclip_port = self.start_owned_with_retry(
            "Paperclip",
            PAPERCLIP_HEALTH,
            Duration::from_secs(90),
            |supervisor, port| supervisor.spawn_paperclip(port),
        )?;
        let paperclip_credentials = self.bootstrap_paperclip(paperclip_port)?;

        status(RuntimeStatus {
            message: "Starting the local agent runtime…".into(),
            error: None,
        });
        let aion_port = self.start_owned_with_retry(
            "AionCore",
            AIONCORE_HEALTH,
            Duration::from_secs(60),
            |supervisor, port| supervisor.spawn_aioncore(port),
        )?;
        wait_for_aioncore_assistant(aion_port, CODEX_ASSISTANT_ID, Duration::from_secs(30))?;
        self.bootstrap_aioncore_mcp(aion_port, paperclip_port)?;

        status(RuntimeStatus {
            message: "Starting OpsWitness…".into(),
            error: None,
        });
        let backend_port = self.start_owned_with_retry(
            "OpsWitness",
            BACKEND_HEALTH,
            Duration::from_secs(60),
            |supervisor, port| {
                supervisor.spawn_backend(port, paperclip_port, aion_port, &paperclip_credentials)
            },
        )?;
        self.backend_url = Some(format!("http://127.0.0.1:{backend_port}"));
        self.persist_instance()?;
        Ok(())
    }

    pub fn begin_draining(&self) -> Result<DrainStatus> {
        let Some(status) = self.backend_drain("begin")? else {
            return Ok(DrainStatus {
                active_work: false,
                backend_confirmed: false,
            });
        };
        if !status.draining {
            bail!("backend did not enter the desktop draining state");
        }
        if status.active_work != !status.active_work_ids.is_empty() {
            bail!("backend returned an inconsistent active Work snapshot");
        }
        Ok(DrainStatus {
            active_work: status.active_work,
            backend_confirmed: true,
        })
    }

    pub fn cancel_draining(&self) -> Result<()> {
        let Some(status) = self.backend_drain("cancel")? else {
            return Ok(());
        };
        if status.draining {
            bail!("backend did not leave the desktop draining state");
        }
        Ok(())
    }

    pub fn stop_all(&mut self) -> Result<()> {
        let mut errors = Vec::new();
        for process in self.processes.iter_mut().rev() {
            if let Err(error) = stop_owned_process(process) {
                errors.push(format!("{}: {error:#}", process.name));
            }
        }
        if !errors.is_empty() {
            bail!(
                "one or more bundled processes did not stop cleanly: {}",
                errors.join("; ")
            );
        }
        self.processes.clear();
        self.backend_url = None;
        match fs::remove_file(&self.instance_file) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(error).with_context(|| {
                    format!(
                        "bundled processes stopped, but the instance descriptor could not be removed: {}",
                        self.instance_file.display()
                    )
                })
            }
        }
        Ok(())
    }

    fn backend_drain(&self, action: &str) -> Result<Option<BackendDrainStatus>> {
        let Some(base) = &self.backend_url else {
            return Ok(None);
        };
        let client = Client::builder().timeout(Duration::from_secs(5)).build()?;
        let bootstrap = client
            .get(format!("{base}{BACKEND_HEALTH}"))
            .send()
            .context("cannot obtain the desktop backend CSRF token")?;
        if !bootstrap.status().is_success() {
            bail!(
                "desktop backend bootstrap failed with HTTP {}",
                bootstrap.status()
            );
        }
        let bootstrap: Value = bootstrap
            .json()
            .context("desktop backend bootstrap returned invalid JSON")?;
        let csrf = bootstrap
            .get("csrf_token")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| anyhow!("desktop backend bootstrap omitted its CSRF token"))?;
        let response = client
            .post(format!("{base}{BACKEND_DRAIN}"))
            .header("X-QD-CSRF", csrf)
            .header("X-OpsWitness-Desktop-Instance", &self.instance_id)
            .json(&serde_json::json!({"action": action}))
            .send()
            .context("desktop backend draining request failed")?;
        if !response.status().is_success() {
            bail!(
                "desktop backend draining request failed with HTTP {}",
                response.status()
            );
        }
        Ok(Some(response.json().context(
            "desktop backend draining response was invalid",
        )?))
    }

    fn require_disk_space(&self, minimum: u64) -> Result<()> {
        let available = fs2::available_space(&self.data_root)?;
        if available < minimum {
            bail!(
                "OpsWitness requires at least 5 GB free; only {:.1} GB is available",
                available as f64 / 1_073_741_824.0
            );
        }
        Ok(())
    }

    fn start_owned_with_retry<F>(
        &mut self,
        name: &str,
        health_path: &str,
        timeout: Duration,
        mut spawn: F,
    ) -> Result<u16>
    where
        F: FnMut(&mut Self, u16) -> Result<()>,
    {
        let mut last_error: Option<anyhow::Error> = None;
        for _ in 0..3 {
            let port = allocate_loopback_port()?;
            let process_count = self.processes.len();
            let attempt = spawn(self, port).and_then(|_| {
                let process = self
                    .processes
                    .last_mut()
                    .context("runtime process was not recorded after spawn")?;
                wait_for_owned_health(process, health_path, timeout)
            });
            match attempt {
                Ok(()) => return Ok(port),
                Err(error) => {
                    if self.processes.len() > process_count {
                        let process = self
                            .processes
                            .last_mut()
                            .context("runtime process disappeared during failed startup")?;
                        if let Err(cleanup_error) = stop_owned_process(process) {
                            self.persist_instance()?;
                            return Err(error.context(format!(
                                "{name} startup failed and its process could not be stopped: \
                                 {cleanup_error:#}"
                            )));
                        }
                        self.processes.pop();
                        self.persist_instance()?;
                    }
                    last_error = Some(error);
                }
            }
        }
        Err(last_error.unwrap_or_else(|| anyhow!("{name} failed to start")))
            .with_context(|| format!("{name} could not claim a private loopback port"))
    }

    fn spawn_paperclip(&mut self, port: u16) -> Result<()> {
        let node = self.resource_payload.join("node/node");
        let cli = self.resource_payload.join("paperclip/dist/index.js");
        let data_dir = self.data_root.join("paperclip");
        let database_port = allocate_loopback_port()?;
        let log = self.log_file("paperclip")?;
        let mut command = self.restricted_command(&node)?;
        command
            .arg(&cli)
            .args([
                "onboard",
                "--yes",
                "--data-dir",
                data_dir
                    .to_str()
                    .ok_or_else(|| anyhow!("invalid Paperclip data path"))?,
                "--bind",
                "loopback",
                "--run",
            ])
            .env("PORT", port.to_string())
            .env(
                "PAPERCLIP_EMBEDDED_POSTGRES_PORT",
                database_port.to_string(),
            )
            .env("PAPERCLIP_TELEMETRY_DISABLED", "1")
            .env("PAPERCLIP_NO_BROWSER", "1")
            .env("PAPERCLIP_HOME", &data_dir);
        self.spawn_owned("paperclip", node, port, command, log)
    }

    fn spawn_aioncore(&mut self, port: u16) -> Result<()> {
        let executable = self.resource_payload.join("aioncore/aioncore");
        let data_dir = self.data_root.join("aion");
        let work_dir = self.data_root.join("workspaces");
        let managed_resources = self.resource_payload.join("aioncore/managed-resources");
        let restricted_path = std::env::join_paths([
            self.resource_payload.join("codex"),
            self.resource_payload.join("node"),
            managed_resources.join("node/bin"),
            managed_resources.join("acp/node_modules/.bin"),
            managed_resources.join("node_modules/.bin"),
            PathBuf::from("/usr/bin"),
            PathBuf::from("/bin"),
            PathBuf::from("/usr/sbin"),
            PathBuf::from("/sbin"),
        ])
        .context("cannot construct the bundled AionCore executable path")?;
        let log = self.log_file("aioncore")?;
        let mut command = self.restricted_command(&executable)?;
        command
            .args([
                "--host",
                "127.0.0.1",
                "--local",
                "--port",
                &port.to_string(),
                "--parent-pid",
                &std::process::id().to_string(),
                "--data-dir",
                data_dir
                    .to_str()
                    .ok_or_else(|| anyhow!("invalid AionCore data path"))?,
                "--work-dir",
                work_dir
                    .to_str()
                    .ok_or_else(|| anyhow!("invalid AionCore work path"))?,
                "--app-version",
                "0.1.45",
                "--log-dir",
                self.log_root
                    .to_str()
                    .ok_or_else(|| anyhow!("invalid AionCore log path"))?,
                "--managed-resources-mode",
                "bundled",
            ])
            .env("AIONUI_BUNDLED_MANAGED_RESOURCES", &managed_resources)
            .env("AIONUI_LOG_DIR", &self.log_root)
            .env("PATH", restricted_path);
        self.spawn_owned("aioncore", executable, port, command, log)
    }

    fn bootstrap_aioncore_mcp(&self, aion_port: u16, paperclip_port: u16) -> Result<()> {
        let base = format!("http://127.0.0.1:{aion_port}");
        let client = Client::builder().timeout(Duration::from_secs(20)).build()?;
        let backend = self.resource_payload.join("backend/opswitness-backend");
        let credential_file = self.data_root.join("runtime-cache/paperclip-service.json");
        let transport = serde_json::json!({
            "type": "stdio",
            "command": backend,
            "args": ["mcp"],
            "env": {
                "OPSWITNESS_DESKTOP_MODE": "1",
                "OPSWITNESS_DESKTOP_CREDENTIAL_FILE": credential_file,
                "OPSWITNESS_APP_SUPPORT_DIR": self.data_root,
                "OPSWITNESS_CONFIG_DIR": self.data_root.join("config"),
                "OPSWITNESS_STATE_DIR": self.data_root.join("state"),
                "OPSWITNESS_LEDGER_DIR": self.data_root.join("state/ledger"),
                "OPSWITNESS_CONSOLE__AIONUI_BASE": base,
                "OPSWITNESS_CONSOLE__CODEX_BIN": self.resource_payload.join("codex/codex"),
                "OPSWITNESS_GATE__CLAUDE_BIN": &self.claude_executable,
                "OPSWITNESS_PAPERCLIP__API_BASE":
                    format!("http://127.0.0.1:{paperclip_port}"),
                "OPSWITNESS_SERVICES__LOG_DIR": self.log_root,
            }
        });
        let desired = serde_json::json!({
            "name": OPSWITNESS_MCP_NAME,
            "description":
                "App-managed OpsWitness evidence, approval, and governance tools. Do not edit.",
            "enabled": false,
            "transport": transport,
        });

        let probe = aion_send(
            &client,
            reqwest::Method::POST,
            &format!("{base}{AIONCORE_MCP_TEST}"),
            &serde_json::json!({
                "name": OPSWITNESS_MCP_NAME,
                "transport": desired["transport"],
            }),
        )?;
        require_opswitness_mcp_tools(&probe)?;

        let listed = aion_get(&client, &format!("{base}{AIONCORE_MCP_SERVERS}"))?;
        let matches = named_aion_mcp_servers(&listed, OPSWITNESS_MCP_NAME)?;
        let server = match matches.as_slice() {
            [] => aion_send(
                &client,
                reqwest::Method::POST,
                &format!("{base}{AIONCORE_MCP_SERVERS}"),
                &desired,
            )?,
            [server] => {
                let server_id = required_string(server, "id", "AionCore MCP server")?;
                aion_send(
                    &client,
                    reqwest::Method::PUT,
                    &format!("{base}{AIONCORE_MCP_SERVERS}/{server_id}"),
                    &desired,
                )?
            }
            _ => bail!("multiple App-managed OpsWitness MCP servers were found"),
        };
        let server_data = aion_data(&server, "MCP create/update")?;
        let server_id = required_string(server_data, "id", "AionCore MCP server")?;
        let enabled = server_data
            .get("enabled")
            .and_then(Value::as_bool)
            .ok_or_else(|| anyhow!("AionCore MCP create/update response omitted enabled state"))?;
        if enabled {
            let disabled = aion_send(
                &client,
                reqwest::Method::POST,
                &format!("{base}{AIONCORE_MCP_SERVERS}/{server_id}/toggle"),
                &serde_json::json!({}),
            )?;
            require_mcp_toggle_state(&disabled, &server_id, false, "MCP disable")?;
        }

        let toggled = aion_send(
            &client,
            reqwest::Method::POST,
            &format!("{base}{AIONCORE_MCP_SERVERS}/{server_id}/toggle"),
            &serde_json::json!({}),
        )?;
        require_mcp_toggle_state(&toggled, &server_id, true, "MCP enable")?;

        let verified = aion_get(
            &client,
            &format!("{base}{AIONCORE_MCP_SERVERS}/{server_id}"),
        )?;
        require_managed_mcp_identity(&verified, &server_id, &backend)?;
        Ok(())
    }

    fn spawn_backend(
        &mut self,
        port: u16,
        paperclip_port: u16,
        aion_port: u16,
        paperclip: &PaperclipCredentials,
    ) -> Result<()> {
        let executable = self.resource_payload.join("backend/opswitness-backend");
        let codex = self.resource_payload.join("codex/codex");
        let log = self.log_file("opswitness")?;
        let mut command = self.restricted_command(&executable)?;
        command
            .args(["console", "serve", "--port", &port.to_string()])
            .env("OPSWITNESS_DESKTOP_MODE", "1")
            .env("OPSWITNESS_APP_SUPPORT_DIR", &self.data_root)
            .env("OPSWITNESS_DESKTOP_RUNTIME_FILE", &self.instance_file)
            .env("OPSWITNESS_CONFIG_DIR", self.data_root.join("config"))
            .env("OPSWITNESS_STATE_DIR", self.data_root.join("state"))
            .env("OPSWITNESS_LEDGER_DIR", self.data_root.join("state/ledger"))
            .env("OPSWITNESS_CONSOLE__EXPOSURE", "loopback")
            .env("OPSWITNESS_CONSOLE__HOST", "127.0.0.1")
            .env("OPSWITNESS_CONSOLE__PORT", port.to_string())
            .env(
                "OPSWITNESS_CONSOLE__AIONUI_BASE",
                format!("http://127.0.0.1:{aion_port}"),
            )
            .env("OPSWITNESS_CONSOLE__CODEX_BIN", codex)
            .env("OPSWITNESS_GATE__CLAUDE_BIN", &self.claude_executable)
            .env(
                "OPSWITNESS_PAPERCLIP__API_BASE",
                format!("http://127.0.0.1:{paperclip_port}"),
            )
            .env("OPSWITNESS_PAPERCLIP__COMPANY_ID", &paperclip.company_id)
            .env("OPSWITNESS_PAPERCLIP__API_KEY", &paperclip.api_key)
            .env("OPSWITNESS_SERVICES__LOG_DIR", &self.log_root)
            .env("PATH", "/usr/bin:/bin:/usr/sbin:/sbin");
        self.spawn_owned("backend", executable, port, command, log)
    }

    fn restricted_command(&self, executable: &Path) -> Result<Command> {
        let mut command = Command::new(executable);
        command
            .env_clear()
            .env("HOME", &self.data_root)
            .env("CODEX_HOME", self.data_root.join("config/codex"))
            .env("CLAUDE_CONFIG_DIR", self.data_root.join("config/claude"))
            .env("TMPDIR", self.data_root.join("runtime-cache/tmp"))
            .env("XDG_CACHE_HOME", self.data_root.join("runtime-cache"))
            .env("XDG_CONFIG_HOME", self.data_root.join("config"))
            .env("XDG_DATA_HOME", self.data_root.join("state"))
            .env("LANG", "en_US.UTF-8")
            .env("LC_CTYPE", "UTF-8")
            .env("SHELL", "/bin/zsh")
            .env("PATH", "/usr/bin:/bin:/usr/sbin:/sbin");
        Ok(command)
    }

    fn bootstrap_paperclip(&self, port: u16) -> Result<PaperclipCredentials> {
        let base = format!("http://127.0.0.1:{port}");
        let client = Client::builder().timeout(Duration::from_secs(10)).build()?;
        let credential_path = self.data_root.join("runtime-cache/paperclip-service.json");

        if let Some(credentials) = load_optional_credentials(&credential_path)? {
            let companies = api_get(&client, &format!("{base}/api/companies"))?;
            let agents = api_get(
                &client,
                &format!("{base}/api/companies/{}/agents", credentials.company_id),
            )?;
            if array_contains_id(&companies, &credentials.company_id)
                && array_contains_id(&agents, &credentials.agent_id)
                && service_token_is_valid(&client, &base, &credentials)
            {
                return Ok(credentials);
            }
            bail!(
                "the existing Paperclip service credential could not be reconciled; \
                 refusing to create another service token"
            );
        }

        let companies = api_get(&client, &format!("{base}/api/companies"))?;
        let company = select_unique_named(&companies, PAPERCLIP_COMPANY_NAME, "company")?
            .map(Clone::clone)
            .unwrap_or(api_post(
                &client,
                &format!("{base}/api/companies"),
                &serde_json::json!({
                    "name": PAPERCLIP_COMPANY_NAME,
                    "description": "App-managed local governance for OpsWitness"
                }),
            )?);
        let company_id = required_string(&company, "id", "Paperclip company")?;

        let agents = api_get(
            &client,
            &format!("{base}/api/companies/{company_id}/agents"),
        )?;
        let agent = select_managed_agent(&agents)?
            .map(Clone::clone)
            .unwrap_or(api_post(
                &client,
                &format!("{base}/api/companies/{company_id}/agents"),
                &serde_json::json!({
                    "name": PAPERCLIP_AGENT_NAME,
                    "role": "general",
                    "title": "OpsWitness local governance service",
                    "adapterType": "process",
                    "adapterConfig": {},
                    "budgetMonthlyCents": 0,
                    "permissions": {
                        "canCreateAgents": false,
                        "canCreateSkills": false
                    },
                    "metadata": {
                        "opswitnessManaged": true,
                        "opswitnessPurpose": "desktop-service"
                    }
                }),
            )?);
        let agent_id = required_string(&agent, "id", "Paperclip service agent")?;
        let existing_keys = api_get(&client, &format!("{base}/api/agents/{agent_id}/keys"))?;
        if select_unique_named(&existing_keys, PAPERCLIP_TOKEN_NAME, "service token")?.is_some() {
            bail!(
                "an OpsWitness Paperclip service token already exists but the private credential \
                 file is unavailable; refusing to create another token"
            );
        }
        let key = api_post(
            &client,
            &format!("{base}/api/agents/{agent_id}/keys"),
            &serde_json::json!({
                "name": PAPERCLIP_TOKEN_NAME,
                "scope": {"kind": "standard"}
            }),
        )?;
        let api_key = key
            .get("token")
            .or_else(|| key.pointer("/key/token"))
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| anyhow!("Paperclip did not return the new service API key"))?
            .to_owned();
        let credentials = PaperclipCredentials {
            company_id,
            agent_id,
            api_key,
        };
        write_credentials(&credential_path, &credentials)?;
        Ok(credentials)
    }

    fn spawn_owned(
        &mut self,
        name: &'static str,
        executable: PathBuf,
        port: u16,
        mut command: Command,
        log: File,
    ) -> Result<()> {
        let executable = canonical_executable_identity(&executable)
            .with_context(|| format!("cannot establish {name} executable identity before spawn"))?;
        let error_log = log.try_clone()?;
        let child = command
            .stdin(Stdio::null())
            .stdout(Stdio::from(log))
            .stderr(Stdio::from(error_log))
            .spawn()
            .with_context(|| format!("cannot start {name} from {}", executable.display()))?;
        self.processes.push(OwnedProcess {
            name,
            executable,
            port,
            child,
        });
        self.persist_instance()?;
        Ok(())
    }

    fn log_file(&self, name: &str) -> Result<File> {
        use std::os::unix::fs::OpenOptionsExt;

        let path = self.log_root.join(format!("desktop-{name}.log"));
        let file = OpenOptions::new()
            .create(true)
            .append(true)
            .mode(0o600)
            .custom_flags(nix::libc::O_NOFOLLOW)
            .open(&path)
            .with_context(|| format!("cannot open {}", path.display()))?;
        set_private_file(&path)?;
        Ok(file)
    }

    fn persist_instance(&self) -> Result<()> {
        let resource_manifest = self.resource_payload.join("resource-manifest.json");
        let record = InstanceRecord {
            schema_version: 1,
            instance_id: self.instance_id.clone(),
            supervisor_pid: std::process::id(),
            resource_root: self.resource_payload.clone(),
            resource_manifest: resource_manifest.clone(),
            resource_manifest_sha256: sha256_file(&resource_manifest)?,
            codex_executable: self.resource_payload.join("codex/codex"),
            processes: self
                .processes
                .iter()
                .map(|process| ProcessRecord {
                    name: process.name.into(),
                    pid: process.child.id(),
                    executable: process.executable.clone(),
                    port: process.port,
                })
                .collect(),
        };
        atomic_private_write(&self.instance_file, &serde_json::to_vec_pretty(&record)?)?;
        Ok(())
    }
}

impl RuntimeSupervisor for Supervisor {
    fn start(&mut self, status: &mut dyn FnMut(RuntimeStatus)) -> Result<()> {
        Supervisor::start(self, status)
    }

    fn backend_url(&self) -> Option<&str> {
        Supervisor::backend_url(self)
    }

    fn begin_draining(&self) -> Result<DrainStatus> {
        Supervisor::begin_draining(self)
    }

    fn cancel_draining(&self) -> Result<()> {
        Supervisor::cancel_draining(self)
    }

    fn stop_all(&mut self) -> Result<()> {
        Supervisor::stop_all(self)
    }
}

impl Drop for Supervisor {
    fn drop(&mut self) {
        let _ = self.stop_all();
    }
}

fn resolve_bundled_claude_executable(resource_root: &Path) -> Result<PathBuf> {
    use std::os::unix::fs::PermissionsExt;

    let versions_root = resource_root.join("aioncore/managed-resources/acp/claude-agent-acp");
    let root_metadata = fs::symlink_metadata(&versions_root).with_context(|| {
        format!(
            "bundled Claude Agent versions are unavailable: {}",
            versions_root.display()
        )
    })?;
    if root_metadata.file_type().is_symlink() || !root_metadata.is_dir() {
        bail!("bundled Claude Agent versions must be a real directory");
    }
    let canonical_root = fs::canonicalize(&versions_root)
        .context("cannot resolve the bundled Claude Agent versions directory")?;
    let mut matches = Vec::new();
    for entry in
        fs::read_dir(&versions_root).context("cannot inspect bundled Claude Agent versions")?
    {
        let entry = entry.context("cannot inspect a bundled Claude Agent version")?;
        let candidate = entry
            .path()
            .join("darwin-arm64/node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude");
        let metadata = match fs::symlink_metadata(&candidate) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Err(error) => {
                return Err(error).with_context(|| {
                    format!(
                        "cannot inspect bundled Claude executable {}",
                        candidate.display()
                    )
                })
            }
        };
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            bail!("bundled Claude executable must be one regular file");
        }
        if metadata.permissions().mode() & 0o111 == 0 {
            bail!("bundled Claude executable is not executable");
        }
        let resolved = fs::canonicalize(&candidate).with_context(|| {
            format!(
                "cannot resolve bundled Claude executable {}",
                candidate.display()
            )
        })?;
        if !resolved.starts_with(&canonical_root) {
            bail!("bundled Claude executable resolves outside managed resources");
        }
        matches.push(resolved);
    }
    match matches.as_slice() {
        [only] => Ok(only.clone()),
        [] => bail!("exactly one bundled arm64 Claude Agent executable is required; found none"),
        _ => bail!("exactly one bundled arm64 Claude Agent executable is required; found multiple"),
    }
}

fn expected_process_executable(resource_root: &Path, name: &str) -> Result<PathBuf> {
    let relative = match name {
        "paperclip" => "node/node",
        "aioncore" => "aioncore/aioncore",
        "backend" => "backend/opswitness-backend",
        _ => bail!("unknown process in previous desktop instance: {name}"),
    };
    canonical_executable_identity(&resource_root.join(relative))
        .with_context(|| format!("previous desktop executable is unavailable: {relative}"))
}

fn canonical_executable_identity(executable: &Path) -> Result<PathBuf> {
    fs::canonicalize(executable)
        .with_context(|| format!("cannot resolve executable identity: {}", executable.display()))
}

fn executable_identities_match(expected: &Path, observed: &Path) -> Result<bool> {
    Ok(canonical_executable_identity(expected)? == canonical_executable_identity(observed)?)
}

fn private_instance_record(path: &Path) -> Result<InstanceRecord> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    let metadata = fs::symlink_metadata(path)
        .with_context(|| format!("cannot inspect previous instance {}", path.display()))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        bail!("previous desktop instance descriptor is not a regular file");
    }
    if metadata.uid() != unsafe { libc_geteuid() } {
        bail!("previous desktop instance descriptor has the wrong owner");
    }
    if metadata.permissions().mode() & 0o777 != 0o600 {
        bail!("previous desktop instance descriptor must have mode 0600");
    }
    let parent = fs::metadata(
        path.parent()
            .ok_or_else(|| anyhow!("previous instance descriptor has no parent"))?,
    )?;
    if parent.permissions().mode() & 0o077 != 0 {
        bail!("previous desktop instance directory must be private");
    }
    serde_json::from_slice(
        &fs::read(path)
            .with_context(|| format!("cannot read previous instance {}", path.display()))?,
    )
    .context("previous desktop instance descriptor is invalid")
}

#[cfg(target_os = "macos")]
unsafe fn libc_geteuid() -> u32 {
    unsafe extern "C" {
        fn geteuid() -> u32;
    }
    unsafe { geteuid() }
}

#[cfg(not(target_os = "macos"))]
unsafe fn libc_geteuid() -> u32 {
    use std::os::unix::fs::MetadataExt;

    fs::metadata(".")
        .map(|metadata| metadata.uid())
        .unwrap_or(0)
}

#[cfg(target_os = "macos")]
fn process_executable(pid: u32) -> Result<Option<PathBuf>> {
    const BUFFER_SIZE: usize = 4096;
    unsafe extern "C" {
        fn proc_pidpath(pid: c_int, buffer: *mut c_void, buffersize: u32) -> c_int;
    }

    let mut buffer = [0 as c_char; BUFFER_SIZE];
    let length = unsafe {
        proc_pidpath(
            pid as c_int,
            buffer.as_mut_ptr().cast::<c_void>(),
            BUFFER_SIZE as u32,
        )
    };
    if length <= 0 {
        return Ok(None);
    }
    let raw = unsafe { CStr::from_ptr(buffer.as_ptr()) }
        .to_str()
        .context("previous desktop process path is not UTF-8")?;
    Ok(Some(fs::canonicalize(raw).with_context(|| {
        format!("cannot resolve previous desktop process path: {raw}")
    })?))
}

#[cfg(not(target_os = "macos"))]
fn process_executable(pid: u32) -> Result<Option<PathBuf>> {
    let link = PathBuf::from(format!("/proc/{pid}/exe"));
    match fs::read_link(&link) {
        Ok(path) => Ok(Some(fs::canonicalize(path)?)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error).with_context(|| format!("cannot inspect {}", link.display())),
    }
}

fn wait_for_pid_exit(pid: u32, expected: &Path, timeout: Duration) -> Result<bool> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        match process_executable(pid)? {
            None => return Ok(true),
            Some(observed) if observed != expected => {
                bail!(
                    "previous desktop pid {pid} changed identity while stopping; \
                     expected={} observed={}",
                    expected.display(),
                    observed.display()
                )
            }
            Some(_) => thread::sleep(Duration::from_millis(100)),
        }
    }
    Ok(false)
}

fn reconcile_previous_instance(instance_file: &Path, resource_payload: &Path) -> Result<()> {
    match fs::symlink_metadata(instance_file) {
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => {
            return Err(error).with_context(|| {
                format!(
                    "cannot inspect previous instance {}",
                    instance_file.display()
                )
            })
        }
    }
    let record = private_instance_record(instance_file)?;
    if record.schema_version != 1
        || Uuid::parse_str(&record.instance_id).is_err()
        || record.supervisor_pid == 0
    {
        bail!("previous desktop instance identity is invalid");
    }

    let mut seen = BTreeSet::new();
    for process in &record.processes {
        if process.pid == 0 || process.port == 0 || !seen.insert(process.name.as_str()) {
            bail!("previous desktop process descriptor is invalid or duplicated");
        }
    }
    if process_executable(record.supervisor_pid)?.is_some() {
        bail!("previous OpsWitness supervisor pid is still running");
    }
    let mut any_recorded_process_is_running = false;
    for process in &record.processes {
        if process_executable(process.pid)?.is_some() {
            any_recorded_process_is_running = true;
            break;
        }
    }
    if !any_recorded_process_is_running {
        fs::remove_file(instance_file).with_context(|| {
            format!(
                "cannot retire inactive previous instance {}",
                instance_file.display()
            )
        })?;
        return Ok(());
    }

    let resource_root = fs::canonicalize(resource_payload)
        .context("cannot resolve the current desktop resource root")?;
    if fs::canonicalize(&record.resource_root).ok().as_ref() != Some(&resource_root) {
        bail!("previous desktop instance belongs to a different App resource root");
    }
    let expected_manifest = resource_root.join("resource-manifest.json");
    if fs::canonicalize(&record.resource_manifest).ok().as_ref() != Some(&expected_manifest)
        || sha256_file(&expected_manifest)? != record.resource_manifest_sha256
    {
        bail!("previous desktop instance resource manifest identity does not match");
    }
    let expected_codex = fs::canonicalize(resource_root.join("codex/codex"))
        .context("current bundled Codex executable is unavailable")?;
    if fs::canonicalize(&record.codex_executable).ok().as_ref() != Some(&expected_codex) {
        bail!("previous desktop instance Codex executable identity does not match");
    }

    let mut observed_processes: Vec<(ProcessRecord, PathBuf)> = Vec::new();
    for process in &record.processes {
        let expected = expected_process_executable(&resource_root, &process.name)?;
        if fs::canonicalize(&process.executable).ok().as_ref() != Some(&expected) {
            bail!(
                "previous desktop {} executable does not match the current bundle",
                process.name
            );
        }
        if let Some(observed) = process_executable(process.pid)? {
            if observed != expected {
                bail!(
                    "refusing to stop unknown pid {}; expected={} observed={}",
                    process.pid,
                    expected.display(),
                    observed.display()
                );
            }
            observed_processes.push((process.clone(), expected));
        }
    }

    for (process, expected) in observed_processes.iter().rev() {
        let pid = Pid::from_raw(process.pid as i32);
        match process_executable(process.pid)? {
            None => continue,
            Some(observed) if observed != *expected => {
                bail!("refusing to stop a pid whose executable identity changed")
            }
            Some(_) => {}
        }
        if let Err(error) = kill(pid, Signal::SIGTERM) {
            if error == nix::errno::Errno::ESRCH {
                continue;
            }
            return Err(error).with_context(|| {
                format!("cannot stop previous {} pid {}", process.name, process.pid)
            });
        }
        if !wait_for_pid_exit(process.pid, expected, Duration::from_secs(8))? {
            let observed = process_executable(process.pid)?;
            if observed.as_ref() != Some(expected) {
                bail!("refusing to force-stop a pid whose executable identity changed");
            }
            kill(pid, Signal::SIGKILL).with_context(|| {
                format!(
                    "cannot force-stop previous {} pid {}",
                    process.name, process.pid
                )
            })?;
            if !wait_for_pid_exit(process.pid, expected, Duration::from_secs(2))? {
                bail!("previous {} pid {} did not stop", process.name, process.pid);
            }
        }
    }
    fs::remove_file(instance_file).with_context(|| {
        format!(
            "cannot retire previous instance {}",
            instance_file.display()
        )
    })?;
    Ok(())
}

fn allocate_loopback_port() -> Result<u16> {
    let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0))
        .context("cannot reserve a loopback port")?;
    Ok(listener.local_addr()?.port())
}

fn sha256_file(path: &Path) -> Result<String> {
    let mut file = File::open(path).with_context(|| format!("cannot open {}", path.display()))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    Ok(hex::encode(hasher.finalize()))
}

fn aion_get(client: &Client, url: &str) -> Result<Value> {
    let response = client
        .get(url)
        .send()
        .with_context(|| format!("AionCore bootstrap GET failed: {url}"))?;
    if !response.status().is_success() {
        bail!(
            "AionCore bootstrap GET failed with HTTP {}",
            response.status()
        );
    }
    response
        .json()
        .context("AionCore bootstrap returned invalid JSON")
}

fn aion_send(
    client: &Client,
    method: reqwest::Method,
    url: &str,
    payload: &Value,
) -> Result<Value> {
    let response = client
        .request(method, url)
        .json(payload)
        .send()
        .with_context(|| format!("AionCore bootstrap request failed: {url}"))?;
    if !response.status().is_success() {
        bail!(
            "AionCore bootstrap request failed with HTTP {}",
            response.status()
        );
    }
    response
        .json()
        .context("AionCore bootstrap returned invalid JSON")
}

fn aion_data<'a>(payload: &'a Value, operation: &str) -> Result<&'a Value> {
    if payload.get("success").and_then(Value::as_bool) != Some(true) {
        bail!("AionCore {operation} did not report success");
    }
    payload
        .get("data")
        .ok_or_else(|| anyhow!("AionCore {operation} response is missing data"))
}

fn named_aion_mcp_servers<'a>(payload: &'a Value, name: &str) -> Result<Vec<&'a Value>> {
    let servers = aion_data(payload, "MCP list")?
        .as_array()
        .ok_or_else(|| anyhow!("AionCore MCP list data is not an array"))?;
    Ok(servers
        .iter()
        .filter(|server| server.get("name").and_then(Value::as_str) == Some(name))
        .collect())
}

fn require_mcp_toggle_state<'a>(
    payload: &'a Value,
    id: &str,
    enabled: bool,
    operation: &str,
) -> Result<&'a Value> {
    let data = aion_data(payload, operation)?;
    if data.get("id").and_then(Value::as_str) != Some(id)
        || data.get("enabled").and_then(Value::as_bool) != Some(enabled)
    {
        bail!(
            "AionCore did not leave the App-managed MCP server {} after {operation}",
            if enabled { "enabled" } else { "disabled" }
        );
    }
    Ok(data)
}

fn require_opswitness_mcp_tools(payload: &Value) -> Result<()> {
    let data = aion_data(payload, "MCP connection test")?;
    if data.get("success").and_then(Value::as_bool) != Some(true) {
        bail!("AionCore could not initialize the bundled OpsWitness MCP server");
    }
    let tools = data
        .get("tools")
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow!("AionCore MCP connection test did not return tools"))?;
    let available: BTreeSet<&str> = tools
        .iter()
        .filter_map(|tool| tool.get("name").and_then(Value::as_str))
        .collect();
    let missing: Vec<&str> = OPSWITNESS_MCP_TOOLS
        .iter()
        .copied()
        .filter(|name| !available.contains(name))
        .collect();
    if !missing.is_empty() {
        bail!("bundled OpsWitness MCP is missing required tools: {missing:?}");
    }
    Ok(())
}

fn require_managed_mcp_identity(payload: &Value, id: &str, backend: &Path) -> Result<()> {
    let data = aion_data(payload, "MCP readback")?;
    if data.get("id").and_then(Value::as_str) != Some(id)
        || data.get("name").and_then(Value::as_str) != Some(OPSWITNESS_MCP_NAME)
        || data.get("enabled").and_then(Value::as_bool) != Some(true)
        || data.get("builtin").and_then(Value::as_bool) != Some(false)
    {
        bail!("App-managed OpsWitness MCP identity or enabled state changed during bootstrap");
    }
    let transport = data
        .get("transport")
        .ok_or_else(|| anyhow!("App-managed OpsWitness MCP transport is missing"))?;
    let expected_command = backend
        .to_str()
        .ok_or_else(|| anyhow!("bundled backend path is not UTF-8"))?;
    let expected_args = serde_json::json!(["mcp"]);
    if transport.get("type").and_then(Value::as_str) != Some("stdio")
        || transport.get("command").and_then(Value::as_str) != Some(expected_command)
        || transport.get("args") != Some(&expected_args)
    {
        bail!("App-managed OpsWitness MCP transport failed exact readback");
    }
    Ok(())
}

fn api_get(client: &Client, url: &str) -> Result<Value> {
    let response = client
        .get(url)
        .send()
        .with_context(|| format!("Paperclip bootstrap GET failed: {url}"))?;
    if !response.status().is_success() {
        bail!(
            "Paperclip bootstrap GET failed with HTTP {}",
            response.status()
        );
    }
    response
        .json()
        .context("Paperclip bootstrap returned invalid JSON")
}

fn api_post(client: &Client, url: &str, payload: &Value) -> Result<Value> {
    let response = client
        .post(url)
        .json(payload)
        .send()
        .with_context(|| format!("Paperclip bootstrap POST failed: {url}"))?;
    if !response.status().is_success() {
        bail!(
            "Paperclip bootstrap POST failed with HTTP {}",
            response.status()
        );
    }
    response
        .json()
        .context("Paperclip bootstrap returned invalid JSON")
}

fn service_token_is_valid(client: &Client, base: &str, credentials: &PaperclipCredentials) -> bool {
    let response = client
        .get(format!("{base}/api/agents/me"))
        .bearer_auth(&credentials.api_key)
        .send();
    let Ok(response) = response else {
        return false;
    };
    if !response.status().is_success() {
        return false;
    }
    response
        .json::<Value>()
        .ok()
        .and_then(|value| value.get("id").and_then(Value::as_str).map(str::to_owned))
        .as_deref()
        == Some(credentials.agent_id.as_str())
}

fn values_array(value: &Value) -> Option<&Vec<Value>> {
    value
        .as_array()
        .or_else(|| value.get("data").and_then(Value::as_array))
}

fn array_contains_id(value: &Value, identifier: &str) -> bool {
    values_array(value).is_some_and(|items| {
        items
            .iter()
            .any(|item| item.get("id").and_then(Value::as_str) == Some(identifier))
    })
}

fn select_unique_named<'a>(
    value: &'a Value,
    expected_name: &str,
    kind: &str,
) -> Result<Option<&'a Value>> {
    let items =
        values_array(value).ok_or_else(|| anyhow!("Paperclip {kind} list was not an array"))?;
    let matches: Vec<_> = items
        .iter()
        .filter(|item| item.get("name").and_then(Value::as_str) == Some(expected_name))
        .collect();
    match matches.as_slice() {
        [] => Ok(None),
        [found] => Ok(Some(*found)),
        _ => bail!("multiple Paperclip {kind} records are named {expected_name:?}"),
    }
}

fn select_managed_agent(value: &Value) -> Result<Option<&Value>> {
    let items =
        values_array(value).ok_or_else(|| anyhow!("Paperclip agent list was not an array"))?;
    let matches: Vec<_> = items
        .iter()
        .filter(|item| {
            item.pointer("/metadata/opswitnessManaged")
                .and_then(Value::as_bool)
                == Some(true)
        })
        .collect();
    match matches.as_slice() {
        [] => select_unique_named(value, PAPERCLIP_AGENT_NAME, "agent"),
        [found] => Ok(Some(*found)),
        _ => bail!("multiple Paperclip agents carry the OpsWitness managed marker"),
    }
}

fn required_string(value: &Value, key: &str, label: &str) -> Result<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .filter(|field| !field.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| anyhow!("{label} response is missing {key}"))
}

fn read_credentials(path: &Path) -> Result<PaperclipCredentials> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    let metadata =
        fs::symlink_metadata(path).with_context(|| format!("cannot inspect {}", path.display()))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        bail!("Paperclip service credential must be a regular file");
    }
    if metadata.uid() != unsafe { libc_geteuid() } || metadata.permissions().mode() & 0o777 != 0o600
    {
        bail!("Paperclip service credential ownership or mode is unsafe");
    }
    let credentials: PaperclipCredentials = serde_json::from_slice(
        &fs::read(path).with_context(|| format!("cannot read {}", path.display()))?,
    )
    .context("invalid Paperclip service credential file")?;
    if credentials.company_id.is_empty()
        || credentials.agent_id.is_empty()
        || credentials.api_key.is_empty()
    {
        bail!("Paperclip service credential file is incomplete");
    }
    Ok(credentials)
}

fn load_optional_credentials(path: &Path) -> Result<Option<PaperclipCredentials>> {
    match fs::symlink_metadata(path) {
        Ok(_) => read_credentials(path).map(Some),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error)
            .with_context(|| format!("cannot inspect Paperclip credential {}", path.display())),
    }
}

fn write_credentials(path: &Path, credentials: &PaperclipCredentials) -> Result<()> {
    atomic_private_write(path, &serde_json::to_vec(credentials)?)
}

fn atomic_private_write(path: &Path, contents: &[u8]) -> Result<()> {
    use std::os::unix::fs::OpenOptionsExt;

    let parent = path
        .parent()
        .ok_or_else(|| anyhow!("private state path has no parent"))?;
    let name = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| anyhow!("private state filename is invalid"))?;
    let temporary = parent.join(format!(".{name}.{}.tmp", Uuid::new_v4()));
    let result = (|| -> Result<()> {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .open(&temporary)
            .with_context(|| format!("cannot create {}", temporary.display()))?;
        file.write_all(contents)?;
        file.sync_all()?;
        fs::rename(&temporary, path)?;
        File::open(parent)?.sync_all()?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

#[cfg(unix)]
fn set_private_directory(path: &Path) -> Result<()> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};
    let metadata =
        fs::symlink_metadata(path).with_context(|| format!("cannot inspect {}", path.display()))?;
    if metadata.file_type().is_symlink()
        || !metadata.is_dir()
        || metadata.uid() != unsafe { libc_geteuid() }
    {
        bail!("private runtime directory ownership or type is unsafe");
    }
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))
        .with_context(|| format!("cannot secure {}", path.display()))
}

#[cfg(unix)]
fn set_private_file(path: &Path) -> Result<()> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};
    let metadata =
        fs::symlink_metadata(path).with_context(|| format!("cannot inspect {}", path.display()))?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || metadata.uid() != unsafe { libc_geteuid() }
    {
        bail!("private runtime file ownership or type is unsafe");
    }
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))
        .with_context(|| format!("cannot secure {}", path.display()))
}

#[cfg(target_os = "macos")]
fn lsof_reports_loopback_listener(report: &str, port: u16) -> bool {
    let expected_port = port.to_string();
    report.lines().any(|line| {
        line.strip_prefix('n').is_some_and(|address| {
            address
                .rsplit_once(':')
                .is_some_and(|(_, observed_port)| observed_port == expected_port)
                && (address.starts_with("127.0.0.1:") || address.starts_with("localhost:"))
        })
    })
}

#[cfg(target_os = "macos")]
fn process_owns_listener(pid: u32, port: u16) -> Result<bool> {
    let output = Command::new("/usr/sbin/lsof")
        .args([
            "-nP",
            "-a",
            "-p",
            &pid.to_string(),
            "-iTCP",
            "-sTCP:LISTEN",
            "-Fpn",
        ])
        .output()
        .context("cannot inspect the loopback listener owner")?;
    if !output.status.success() {
        return Ok(false);
    }
    let report = String::from_utf8(output.stdout).context("lsof returned non-UTF-8 output")?;
    Ok(lsof_reports_loopback_listener(&report, port))
}

#[cfg(not(target_os = "macos"))]
fn process_owns_listener(_pid: u32, _port: u16) -> Result<bool> {
    Ok(true)
}

fn wait_for_owned_health(process: &mut OwnedProcess, path: &str, timeout: Duration) -> Result<()> {
    let client = Client::builder().timeout(Duration::from_secs(2)).build()?;
    let deadline = Instant::now() + timeout;
    let url = format!("http://127.0.0.1:{}{path}", process.port);
    while Instant::now() < deadline {
        if let Some(status) = process.child.try_wait()? {
            bail!(
                "{} exited before health was established with status {status}",
                process.name
            );
        }
        match client.get(&url).send() {
            Ok(response)
                if response.status().is_success()
                    && process_owns_listener(process.child.id(), process.port)? =>
            {
                return Ok(())
            }
            _ => thread::sleep(Duration::from_millis(250)),
        }
    }
    bail!(
        "{} did not become healthy on a listener owned by pid {}",
        process.name,
        process.child.id()
    )
}

fn wait_for_aioncore_assistant(port: u16, assistant_id: &str, timeout: Duration) -> Result<()> {
    let client = Client::builder().timeout(Duration::from_secs(2)).build()?;
    let deadline = Instant::now() + timeout;
    let url = format!("http://127.0.0.1:{port}{AIONCORE_ASSISTANTS}");
    while Instant::now() < deadline {
        let ready = client
            .get(&url)
            .send()
            .ok()
            .filter(|response| response.status().is_success())
            .and_then(|response| response.json::<Value>().ok())
            .and_then(|payload| payload.get("data").and_then(Value::as_array).cloned())
            .is_some_and(|assistants| {
                assistants.iter().any(|assistant| {
                    assistant.get("id").and_then(Value::as_str) == Some(assistant_id)
                        && assistant.get("enabled").and_then(Value::as_bool) == Some(true)
                        && assistant.get("team_selectable").and_then(Value::as_bool) == Some(true)
                })
            });
        if ready {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(250));
    }
    bail!("AionCore is online, but the bundled Codex assistant {assistant_id} did not become ready")
}

fn stop_owned_process(process: &mut OwnedProcess) -> Result<()> {
    if process
        .child
        .try_wait()
        .with_context(|| format!("cannot inspect {} before shutdown", process.name))?
        .is_some()
    {
        return Ok(());
    }
    let pid = process.child.id();
    match process_executable(pid)? {
        None => {
            let _ = process.child.try_wait();
            return Ok(());
        }
        Some(observed)
            if !executable_identities_match(&process.executable, &observed)
                .with_context(|| format!("cannot compare {} executable identity", process.name))? =>
        {
            bail!(
                "refusing to stop pid {pid}; expected={} observed={}",
                process.executable.display(),
                observed.display()
            )
        }
        Some(_) => {}
    }
    kill(Pid::from_raw(pid as i32), Signal::SIGTERM)
        .with_context(|| format!("cannot send SIGTERM to {} pid {pid}", process.name))?;
    let deadline = Instant::now() + Duration::from_secs(8);
    while Instant::now() < deadline {
        if process
            .child
            .try_wait()
            .with_context(|| format!("cannot wait for {} pid {pid}", process.name))?
            .is_some()
        {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(100));
    }
    match process_executable(pid)? {
        None => {
            let _ = process.child.try_wait();
            return Ok(());
        }
        Some(observed)
            if !executable_identities_match(&process.executable, &observed)
                .with_context(|| format!("cannot compare {} executable identity", process.name))? =>
        {
            bail!(
                "refusing to force-stop pid {pid}; expected={} observed={}",
                process.executable.display(),
                observed.display()
            )
        }
        Some(_) => {}
    }
    process
        .child
        .kill()
        .with_context(|| format!("cannot force-stop {} pid {pid}", process.name))?;
    process
        .child
        .wait()
        .with_context(|| format!("cannot reap {} pid {pid}", process.name))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    #[cfg(target_os = "macos")]
    use super::lsof_reports_loopback_listener;
    use super::{
        canonical_executable_identity, executable_identities_match, expected_process_executable,
        load_optional_credentials, named_aion_mcp_servers, reconcile_previous_instance,
        require_managed_mcp_identity, require_mcp_toggle_state, require_opswitness_mcp_tools,
        resolve_bundled_claude_executable, select_managed_agent, select_unique_named,
        stop_owned_process, InstanceRecord, OwnedProcess, PaperclipCredentials, ProcessRecord,
        OPSWITNESS_MCP_NAME, OPSWITNESS_MCP_TOOLS,
    };
    use serde_json::json;
    use std::{
        fs,
        os::unix::fs::{symlink, PermissionsExt},
        path::Path,
        process::{Command, Stdio},
    };
    use uuid::Uuid;

    #[cfg(target_os = "macos")]
    #[test]
    fn listener_identity_accepts_only_the_exact_ipv4_loopback_port() {
        let report = "p123\nn127.0.0.1:49152\nn*:8000\nn[::1]:9000\n";
        assert!(lsof_reports_loopback_listener(report, 49152));
        assert!(!lsof_reports_loopback_listener(report, 8000));
        assert!(!lsof_reports_loopback_listener(report, 9000));
    }

    #[test]
    fn paperclip_bootstrap_selection_is_idempotent_and_ambiguous_names_fail() {
        let companies = json!([{"id": "company-1", "name": "OpsWitness"}]);
        assert_eq!(
            select_unique_named(&companies, "OpsWitness", "company")
                .unwrap()
                .unwrap()["id"],
            "company-1"
        );
        let duplicates = json!([
            {"id": "company-1", "name": "OpsWitness"},
            {"id": "company-2", "name": "OpsWitness"}
        ]);
        assert!(select_unique_named(&duplicates, "OpsWitness", "company").is_err());

        let agents = json!([
            {
                "id": "agent-1",
                "name": "Renamed Service",
                "metadata": {"opswitnessManaged": true}
            }
        ]);
        assert_eq!(
            select_managed_agent(&agents).unwrap().unwrap()["id"],
            "agent-1"
        );
        let keys = json!([{"id": "key-1", "name": "opswitness-desktop"}]);
        assert_eq!(
            select_unique_named(&keys, "opswitness-desktop", "service token")
                .unwrap()
                .unwrap()["id"],
            "key-1"
        );
    }

    #[test]
    fn paperclip_credentials_distinguish_absent_from_corrupt_or_unsafe() {
        let root =
            std::env::temp_dir().join(format!("opswitness-credential-test-{}", Uuid::new_v4()));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let path = root.join("paperclip-service.json");
        assert!(load_optional_credentials(&path).unwrap().is_none());

        fs::write(&path, b"{not-json").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(load_optional_credentials(&path).is_err());

        fs::write(
            &path,
            serde_json::to_vec(&PaperclipCredentials {
                company_id: "company-1".into(),
                agent_id: "agent-1".into(),
                api_key: "secret".into(),
            })
            .unwrap(),
        )
        .unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(load_optional_credentials(&path).is_err());

        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(load_optional_credentials(&path).unwrap().is_some());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn orphan_recovery_rejects_unknown_process_names_before_signalling() {
        assert!(expected_process_executable(Path::new("/tmp"), "postgres").is_err());
    }

    #[test]
    fn bundled_claude_resolution_is_exact_executable_and_not_a_symlink() {
        let root =
            std::env::temp_dir().join(format!("opswitness-claude-runtime-{}", Uuid::new_v4()));
        let candidate = root.join(
            "aioncore/managed-resources/acp/claude-agent-acp/0.58.1/darwin-arm64/node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude",
        );
        fs::create_dir_all(candidate.parent().unwrap()).unwrap();
        fs::write(&candidate, b"arm64-placeholder").unwrap();
        fs::set_permissions(&candidate, fs::Permissions::from_mode(0o700)).unwrap();

        assert_eq!(
            resolve_bundled_claude_executable(&root).unwrap(),
            fs::canonicalize(&candidate).unwrap()
        );

        fs::remove_file(&candidate).unwrap();
        let outside = root.join("outside-claude");
        fs::write(&outside, b"outside").unwrap();
        fs::set_permissions(&outside, fs::Permissions::from_mode(0o700)).unwrap();
        symlink(&outside, &candidate).unwrap();
        assert!(resolve_bundled_claude_executable(&root).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn bundled_claude_resolution_rejects_ambiguous_versions() {
        let root =
            std::env::temp_dir().join(format!("opswitness-claude-ambiguous-{}", Uuid::new_v4()));
        for version in ["0.58.1", "0.59.0"] {
            let candidate = root.join(format!(
                "aioncore/managed-resources/acp/claude-agent-acp/{version}/darwin-arm64/node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude"
            ));
            fs::create_dir_all(candidate.parent().unwrap()).unwrap();
            fs::write(&candidate, b"arm64-placeholder").unwrap();
            fs::set_permissions(&candidate, fs::Permissions::from_mode(0o700)).unwrap();
        }

        assert!(resolve_bundled_claude_executable(&root)
            .unwrap_err()
            .to_string()
            .contains("found multiple"));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn executable_identity_normalizes_symlink_aliases_and_rejects_unknown_files() {
        let root =
            std::env::temp_dir().join(format!("opswitness-executable-identity-{}", Uuid::new_v4()));
        fs::create_dir(&root).unwrap();
        let executable = root.join("executable");
        let alias = root.join("executable-alias");
        let unknown = root.join("unknown");
        fs::write(&executable, b"known").unwrap();
        fs::write(&unknown, b"unknown").unwrap();
        symlink(&executable, &alias).unwrap();

        let canonical = canonical_executable_identity(&executable).unwrap();
        assert_eq!(canonical_executable_identity(&alias).unwrap(), canonical);
        assert!(executable_identities_match(&canonical, &alias).unwrap());
        assert!(!executable_identities_match(&canonical, &unknown).unwrap());

        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn executable_identity_normalizes_tmp_and_private_tmp_aliases() {
        let name = format!("opswitness-tmp-identity-{}", Uuid::new_v4());
        let public_root = Path::new("/tmp").join(&name);
        let private_root = Path::new("/private/tmp").join(&name);
        fs::create_dir(&public_root).unwrap();
        let public_executable = public_root.join("executable");
        let private_executable = private_root.join("executable");
        fs::write(&public_executable, b"same-vnode").unwrap();

        assert!(executable_identities_match(&public_executable, &private_executable).unwrap());
        assert_eq!(
            canonical_executable_identity(&public_executable).unwrap(),
            private_executable
        );

        fs::remove_dir_all(public_root).unwrap();
    }

    #[test]
    fn owned_process_shutdown_refuses_an_unknown_executable_without_signalling_it() {
        let child = Command::new("/bin/sleep")
            .arg("30")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let mut process = OwnedProcess {
            name: "identity-test",
            executable: canonical_executable_identity(Path::new("/bin/cat")).unwrap(),
            port: 49152,
            child,
        };

        let error = stop_owned_process(&mut process).unwrap_err();

        assert!(error.to_string().contains("refusing to stop pid"));
        assert!(process.child.try_wait().unwrap().is_none());
        process.child.kill().unwrap();
        process.child.wait().unwrap();
    }

    #[test]
    fn inactive_previous_build_descriptor_is_retired_without_taking_over_processes() {
        let root =
            std::env::temp_dir().join(format!("opswitness-inactive-instance-{}", Uuid::new_v4()));
        let payload = root.join("payload");
        fs::create_dir_all(&payload).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let instance_file = root.join("instance.json");
        let record = InstanceRecord {
            schema_version: 1,
            instance_id: Uuid::new_v4().to_string(),
            supervisor_pid: u32::MAX,
            resource_root: payload.clone(),
            resource_manifest: payload.join("resource-manifest.json"),
            resource_manifest_sha256: "different-build".into(),
            codex_executable: payload.join("codex/codex"),
            processes: Vec::new(),
        };
        fs::write(&instance_file, serde_json::to_vec(&record).unwrap()).unwrap();
        fs::set_permissions(&instance_file, fs::Permissions::from_mode(0o600)).unwrap();

        reconcile_previous_instance(&instance_file, &payload).unwrap();

        assert!(!instance_file.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn previous_build_descriptor_with_a_live_pid_remains_fail_closed() {
        let root =
            std::env::temp_dir().join(format!("opswitness-live-instance-{}", Uuid::new_v4()));
        let payload = root.join("payload");
        fs::create_dir_all(&payload).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let manifest = payload.join("resource-manifest.json");
        fs::write(&manifest, b"new-build").unwrap();
        let instance_file = root.join("instance.json");
        let record = InstanceRecord {
            schema_version: 1,
            instance_id: Uuid::new_v4().to_string(),
            supervisor_pid: u32::MAX,
            resource_root: payload.clone(),
            resource_manifest: manifest,
            resource_manifest_sha256: "different-build".into(),
            codex_executable: payload.join("codex/codex"),
            processes: vec![ProcessRecord {
                name: "backend".into(),
                pid: std::process::id(),
                executable: payload.join("backend/opswitness-backend"),
                port: 49152,
            }],
        };
        fs::write(&instance_file, serde_json::to_vec(&record).unwrap()).unwrap();
        fs::set_permissions(&instance_file, fs::Permissions::from_mode(0o600)).unwrap();

        let error = reconcile_previous_instance(&instance_file, &payload).unwrap_err();

        assert!(error
            .to_string()
            .contains("resource manifest identity does not match"));
        assert!(instance_file.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn managed_mcp_probe_requires_the_complete_tool_contract() {
        let tools: Vec<_> = OPSWITNESS_MCP_TOOLS
            .iter()
            .map(|name| json!({"name": name}))
            .collect();
        let complete = json!({"success": true, "data": {"success": true, "tools": tools}});
        require_opswitness_mcp_tools(&complete).unwrap();

        let incomplete = json!({
            "success": true,
            "data": {"success": true, "tools": [{"name": "qd_artifact_verify"}]}
        });
        assert!(require_opswitness_mcp_tools(&incomplete).is_err());
    }

    #[test]
    fn managed_mcp_readback_is_exact_and_duplicate_names_fail() {
        let backend = Path::new("/Applications/OpsWitness.app/backend/opswitness-backend");
        let readback = json!({
            "success": true,
            "data": {
                "id": "mcp-managed",
                "name": OPSWITNESS_MCP_NAME,
                "enabled": true,
                "builtin": false,
                "transport": {
                    "type": "stdio",
                    "command": backend,
                    "args": ["mcp"]
                }
            }
        });
        require_managed_mcp_identity(&readback, "mcp-managed", backend).unwrap();

        let duplicate_list = json!({
            "success": true,
            "data": [
                {"id": "one", "name": OPSWITNESS_MCP_NAME},
                {"id": "two", "name": OPSWITNESS_MCP_NAME}
            ]
        });
        assert_eq!(
            named_aion_mcp_servers(&duplicate_list, OPSWITNESS_MCP_NAME)
                .unwrap()
                .len(),
            2
        );
    }

    #[test]
    fn managed_mcp_toggle_requires_the_expected_identity_and_state() {
        let disabled = json!({
            "success": true,
            "data": {"id": "mcp-managed", "enabled": false}
        });
        require_mcp_toggle_state(&disabled, "mcp-managed", false, "MCP disable").unwrap();

        assert!(require_mcp_toggle_state(&disabled, "mcp-managed", true, "MCP enable").is_err());
        assert!(require_mcp_toggle_state(&disabled, "different-id", false, "MCP disable").is_err());
    }
}
