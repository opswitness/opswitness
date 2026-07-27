#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod manifest;
mod supervisor;
mod updater;

use anyhow::{Context, Result};
use rfd::{MessageButtons, MessageDialog, MessageDialogResult, MessageLevel};
use serde_json::json;
use std::{
    fs,
    net::{Ipv4Addr, SocketAddrV4, TcpListener},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
};
use supervisor::{DrainStatus, RuntimeStatus, RuntimeSupervisor, Supervisor};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    webview::PageLoadEvent,
    Manager, RunEvent, WindowEvent,
};
use uuid::Uuid;

const APP_QUIT_MENU_ID: &str = "opswitness_controlled_quit";

struct DesktopState {
    supervisor: Arc<Mutex<Box<dyn RuntimeSupervisor>>>,
    resource_root: Option<PathBuf>,
    resource_error: Option<String>,
    runtime_status: Mutex<RuntimeStatus>,
    startup_started: AtomicBool,
    startup_cancelled: AtomicBool,
    quitting: AtomicBool,
    updating: AtomicBool,
    drain_operation: AtomicBool,
    update_check_running: AtomicBool,
}

struct UnavailableSupervisor {
    error: String,
}

impl RuntimeSupervisor for UnavailableSupervisor {
    fn start(&mut self, _status: &mut dyn FnMut(RuntimeStatus)) -> Result<()> {
        anyhow::bail!("{}", self.error)
    }

    fn backend_url(&self) -> Option<&str> {
        None
    }

    fn begin_draining(&self) -> Result<DrainStatus> {
        Ok(DrainStatus {
            active_work: false,
            backend_confirmed: false,
        })
    }

    fn cancel_draining(&self) -> Result<()> {
        Ok(())
    }

    fn stop_all(&mut self) -> Result<()> {
        Ok(())
    }
}

struct SmokeDirectory(PathBuf);

impl Drop for SmokeDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn application_data_root() -> Result<PathBuf> {
    let home = dirs::home_dir().context("cannot locate the user home directory")?;
    Ok(home.join("Library/Application Support/OpsWitness"))
}

fn application_log_root() -> Result<PathBuf> {
    let home = dirs::home_dir().context("cannot locate the user home directory")?;
    Ok(home.join("Library/Logs/OpsWitness"))
}

fn show_main(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn update_shell(app: &tauri::AppHandle, payload: &RuntimeStatus) {
    if let Some(state) = app.try_state::<DesktopState>() {
        if let Ok(mut current) = state.runtime_status.lock() {
            *current = payload.clone();
        }
    }
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let message = serde_json::to_string(&payload.message).unwrap_or_else(|_| "\"\"".into());
    let error = serde_json::to_string(&payload.error).unwrap_or_else(|_| "null".into());
    let script = format!(
        "if (window.opswitnessShellReady) {{ \
         document.querySelector('#status').textContent = {message}; \
         const detail = document.querySelector('#detail'); \
         const error = {error}; \
         if (error) {{ detail.textContent = error; detail.hidden = false; }} \
         }}"
    );
    let _ = window.eval(&script);
}

fn startup_error(error: &anyhow::Error) -> String {
    let details = format!("{error:#}");
    if details.contains("previous desktop instance resource manifest identity does not match") {
        return format!(
            "A previous version of OpsWitness is still running in the background. \
             OpsWitness left your data and active Work untouched because it could not safely \
             take over processes from a different App build.\n\n\
             Restart this Mac, then reopen OpsWitness. The stale instance record will be \
             retired after its processes have stopped.\n\nTechnical details: {details}"
        );
    }
    format!(
        "OpsWitness could not safely start its bundled runtime. Your data was left untouched.\n\n\
         Technical details: {details}"
    )
}

fn prepare_supervisor(resource_root: &Path) -> Result<Supervisor> {
    manifest::verify_runtime(resource_root)?;
    Supervisor::new(
        resource_root.join("payload"),
        application_data_root()?,
        application_log_root()?,
    )
}

fn start_supervisor(
    supervisor: &mut dyn RuntimeSupervisor,
    emit: &mut dyn FnMut(RuntimeStatus),
) -> Result<Option<String>> {
    match supervisor.start(emit) {
        Ok(()) => Ok(supervisor.backend_url().map(str::to_owned)),
        Err(error) => {
            match supervisor.stop_all() {
                Ok(()) => Err(error),
                Err(cleanup_error) => Err(error.context(format!(
                    "runtime startup cleanup also failed: {cleanup_error:#}"
                ))),
            }
        }
    }
}

fn distribution_smoke_test() -> Result<()> {
    let executable = std::env::current_exe().context("cannot locate desktop executable")?;
    let contents = executable
        .parent()
        .and_then(|macos| macos.parent())
        .context("desktop executable is not inside a macOS app bundle")?;
    let resource_root = contents.join("Resources/runtime");
    manifest::verify_runtime(&resource_root)?;
    let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0))
        .context("cannot bind a dynamic loopback port")?;
    let address = listener.local_addr()?;
    if !address.ip().is_loopback() {
        anyhow::bail!("distribution smoke listener did not bind to loopback");
    }
    drop(listener);

    let smoke_root =
        std::env::temp_dir().join(format!("opswitness-distribution-smoke-{}", Uuid::new_v4()));
    fs::create_dir(&smoke_root)
        .with_context(|| format!("cannot create clean smoke root {}", smoke_root.display()))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&smoke_root, fs::Permissions::from_mode(0o700))?;
    }
    let _cleanup = SmokeDirectory(smoke_root.clone());
    let clean_home = smoke_root.join("home");
    fs::create_dir(&clean_home)?;
    std::env::set_var("HOME", &clean_home);
    std::env::set_var(
        "OPSWITNESS_LEGACY_CONFIG_DIR",
        smoke_root.join("absent-legacy-config"),
    );
    std::env::set_var(
        "OPSWITNESS_LEGACY_STATE_DIR",
        smoke_root.join("absent-legacy-state"),
    );

    let mut supervisor = Supervisor::new(
        resource_root.join("payload"),
        smoke_root.join("app-support"),
        smoke_root.join("logs"),
    )?;
    supervisor.start(|_| {})?;
    let backend_url = supervisor
        .backend_url()
        .context("distribution smoke backend did not expose a URL")?
        .to_owned();
    let parsed = url::Url::parse(&backend_url)?;
    if parsed.host_str() != Some("127.0.0.1") {
        anyhow::bail!("distribution smoke backend was not bound to IPv4 loopback");
    }
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()?;
    for endpoint in ["/api/v1/bootstrap", "/api/v1/onboarding"] {
        let response = client
            .get(format!("{backend_url}{endpoint}"))
            .send()
            .with_context(|| format!("clean-home smoke request failed: {endpoint}"))?;
        if !response.status().is_success() {
            anyhow::bail!(
                "clean-home smoke request {endpoint} failed with HTTP {}",
                response.status()
            );
        }
        response
            .json::<serde_json::Value>()
            .with_context(|| format!("clean-home smoke response was not JSON: {endpoint}"))?;
    }
    supervisor
        .stop_all()
        .context("distribution smoke could not stop every bundled process")?;
    println!(
        "{}",
        serde_json::to_string(&json!({
            "healthy": true,
            "resource_inventory": "verified",
            "bind_address": parsed.host_str(),
            "target": "aarch64-apple-darwin",
            "services_started": true,
            "clean_home": true,
            "runtime_chain": ["embedded-postgres", "paperclip", "aioncore", "opswitness-backend"],
            "first_work": "requires manual exact-DMG ChatGPT login evidence"
        }))?
    );
    Ok(())
}

fn confirm_quit(active_work: bool) -> bool {
    if !active_work {
        return true;
    }
    MessageDialog::new()
        .set_level(MessageLevel::Warning)
        .set_title("Quit OpsWitness?")
        .set_description(
            "A Work may still be active. Quitting stops the bundled runtimes. \
             The Work can be reconciled when OpsWitness starts again.",
        )
        .set_buttons(MessageButtons::OkCancelCustom(
            "Quit".into(),
            "Keep Running".into(),
        ))
        .show()
        == MessageDialogResult::Ok
}

fn try_begin_drain_operation(app: &tauri::AppHandle) -> bool {
    app.state::<DesktopState>()
        .drain_operation
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_ok()
}

fn finish_drain_operation(app: &tauri::AppHandle) {
    app.state::<DesktopState>()
        .drain_operation
        .store(false, Ordering::SeqCst);
}

fn begin_desktop_drain(app: &tauri::AppHandle) -> Result<DrainStatus> {
    app.state::<DesktopState>()
        .supervisor
        .lock()
        .map_err(|_| anyhow::anyhow!("runtime supervisor lock is poisoned"))?
        .begin_draining()
}

fn cancel_desktop_drain(app: &tauri::AppHandle) -> Result<()> {
    app.state::<DesktopState>()
        .supervisor
        .lock()
        .map_err(|_| anyhow::anyhow!("runtime supervisor lock is poisoned"))?
        .cancel_draining()
}

fn install_controlled_application_menu(app: &tauri::App) -> Result<()> {
    let menu = Menu::default(app.handle()).context("cannot create the native application menu")?;
    #[cfg(target_os = "macos")]
    {
        let app_menu = menu
            .items()
            .context("cannot inspect the native application menu")?
            .into_iter()
            .next()
            .and_then(|item| item.as_submenu().cloned())
            .context("the native application menu is missing its App submenu")?;
        let item_count = app_menu
            .items()
            .context("cannot inspect the native App submenu")?
            .len();
        if item_count == 0 {
            anyhow::bail!("the native App submenu has no Quit item to replace");
        }
        app_menu
            .remove_at(item_count - 1)
            .context("cannot replace the unsafe native Quit item")?;
        let quit = MenuItem::with_id(
            app,
            APP_QUIT_MENU_ID,
            "Quit OpsWitness…",
            true,
            Some("CmdOrCtrl+Q"),
        )
        .context("cannot create the controlled native Quit item")?;
        app_menu
            .append(&quit)
            .context("cannot install the controlled native Quit item")?;
    }
    app.set_menu(menu)
        .context("cannot activate the controlled native application menu")?;
    Ok(())
}

fn stop_desktop_runtime(app: &tauri::AppHandle) -> Result<()> {
    let state = app.state::<DesktopState>();
    let result = match state.supervisor.lock() {
        Ok(mut supervisor) => supervisor.stop_all(),
        Err(poisoned) => {
            let cleanup = poisoned.into_inner().stop_all();
            match cleanup {
                Ok(()) => anyhow::bail!(
                    "the runtime supervisor state was poisoned; bundled processes were stopped, \
                     but OpsWitness kept the App open instead of assuming shutdown was safe"
                ),
                Err(error) => Err(error.context(
                    "the runtime supervisor state was poisoned and cleanup could not be confirmed",
                )),
            }
        }
    };
    result
}

fn start_desktop_runtime(app: &tauri::AppHandle) {
    let state = app.state::<DesktopState>();
    if state.startup_started.swap(true, Ordering::SeqCst) {
        return;
    }
    let Some(resource_root) = state.resource_root.clone() else {
        update_shell(
            app,
            &RuntimeStatus {
                message: "The bundled runtime could not start.".into(),
                error: state.resource_error.clone(),
            },
        );
        show_main(app);
        return;
    };

    let handle = app.clone();
    std::thread::spawn(move || {
        let state = handle.state::<DesktopState>();
        if state.startup_cancelled.load(Ordering::SeqCst) {
            return;
        }
        update_shell(
            &handle,
            &RuntimeStatus {
                message: "Checking the bundled runtime before starting local services…".into(),
                error: None,
            },
        );
        let supervisor = match prepare_supervisor(&resource_root) {
            Ok(supervisor) => supervisor,
            Err(error) => {
                if !state.startup_cancelled.load(Ordering::SeqCst) {
                    update_shell(
                        &handle,
                        &RuntimeStatus {
                            message: "The bundled runtime could not start.".into(),
                            error: Some(startup_error(&error)),
                        },
                    );
                    show_main(&handle);
                }
                return;
            }
        };
        if state.startup_cancelled.load(Ordering::SeqCst) {
            return;
        }

        let result = state
            .supervisor
            .lock()
            .map_err(|_| anyhow::anyhow!("runtime supervisor lock is poisoned"))
            .and_then(|mut current| {
                if state.startup_cancelled.load(Ordering::SeqCst) {
                    return Ok(None);
                }
                *current = Box::new(supervisor);
                let mut emit = |payload: RuntimeStatus| {
                    update_shell(&handle, &payload);
                };
                start_supervisor(current.as_mut(), &mut emit)
            });
        if state.startup_cancelled.load(Ordering::SeqCst) {
            return;
        }
        match result {
            Ok(Some(url)) => {
                if let Some(window) = handle.get_webview_window("main") {
                    match url.parse() {
                        Ok(parsed) => {
                            if let Err(error) = window.navigate(parsed) {
                                update_shell(
                                    &handle,
                                    &RuntimeStatus {
                                        message:
                                            "OpsWitness is running, but the window could not open."
                                                .into(),
                                        error: Some(error.to_string()),
                                    },
                                );
                            }
                        }
                        Err(error) => {
                            update_shell(
                                &handle,
                                &RuntimeStatus {
                                    message: "The local OpsWitness URL was invalid.".into(),
                                    error: Some(error.to_string()),
                                },
                            );
                        }
                    }
                    let _ = window.show();
                    updater::check_for_updates(handle.clone(), false);
                }
            }
            Ok(None) => {
                update_shell(
                    &handle,
                    &RuntimeStatus {
                        message: "OpsWitness did not report a local address.".into(),
                        error: Some("The backend health gate did not produce a URL.".into()),
                    },
                );
                show_main(&handle);
            }
            Err(error) => {
                update_shell(
                    &handle,
                    &RuntimeStatus {
                        message: "The bundled runtime could not start.".into(),
                        error: Some(error.to_string()),
                    },
                );
                show_main(&handle);
            }
        }
    });
}

fn request_quit(app: &tauri::AppHandle) {
    let state = app.state::<DesktopState>();
    if state.quitting.load(Ordering::SeqCst)
        || state.updating.load(Ordering::SeqCst)
        || !try_begin_drain_operation(app)
    {
        return;
    }
    state.startup_cancelled.store(true, Ordering::SeqCst);
    let drain = match begin_desktop_drain(app) {
        Ok(status) => status,
        Err(error) => {
            state.startup_cancelled.store(false, Ordering::SeqCst);
            finish_drain_operation(app);
            show_main(app);
            MessageDialog::new()
                .set_level(MessageLevel::Error)
                .set_title("OpsWitness could not prepare to quit")
                .set_description(format!(
                    "The local backend could not block new Work dispatches, so OpsWitness kept \
                     running.\n\n{error}"
                ))
                .set_buttons(MessageButtons::Ok)
                .show();
            return;
        }
    };
    if !confirm_quit(drain.active_work) {
        let cancel = cancel_desktop_drain(app);
        state.startup_cancelled.store(false, Ordering::SeqCst);
        finish_drain_operation(app);
        if let Err(error) = cancel {
            show_main(app);
            MessageDialog::new()
                .set_level(MessageLevel::Error)
                .set_title("OpsWitness remains paused for shutdown")
                .set_description(format!(
                    "The backend could not release its dispatch fence. OpsWitness kept running, \
                     but new Work remains blocked until this is resolved.\n\n{error}"
                ))
                .set_buttons(MessageButtons::Ok)
                .show();
        }
        return;
    }
    if let Err(error) = stop_desktop_runtime(app) {
        finish_drain_operation(app);
        show_main(app);
        MessageDialog::new()
            .set_level(MessageLevel::Error)
            .set_title("OpsWitness could not finish quitting")
            .set_description(format!(
                "One or more bundled processes could not be confirmed stopped. OpsWitness kept \
                 the App open and preserved the instance record instead of hiding the problem.\n\n\
                 {error:#}"
            ))
            .set_buttons(MessageButtons::Ok)
            .show();
        return;
    }
    state.quitting.store(true, Ordering::SeqCst);
    finish_drain_operation(app);
    app.exit(0);
}

fn exit_requires_drain(quitting: bool, updating: bool) -> bool {
    !quitting && !updating
}

fn main() {
    if std::env::args().any(|argument| argument == "--distribution-smoke-test") {
        if let Err(error) = distribution_smoke_test() {
            eprintln!(
                "{}",
                serde_json::to_string(&json!({
                    "healthy": false,
                    "error": format!("{error:#}"),
                    "services_started": false
                }))
                .unwrap_or_else(|_| "{\"healthy\":false}".into())
            );
            std::process::exit(1);
        }
        return;
    }

    let application = tauri::Builder::default()
        .on_page_load(|webview, payload| {
            if payload.event() != PageLoadEvent::Finished
                || payload.url().host_str() == Some("127.0.0.1")
            {
                return;
            }
            let app = webview.app_handle();
            let Some(state) = app.try_state::<DesktopState>() else {
                return;
            };
            let Ok(status) = state.runtime_status.lock().map(|status| status.clone()) else {
                return;
            };
            update_shell(app, &status);
        })
        .on_menu_event(|app, event| {
            if event.id().as_ref() == APP_QUIT_MENU_ID {
                request_quit(app);
            }
        })
        .setup(|app| {
            let resource_result = app
                .path()
                .resource_dir()
                .context("cannot locate the application resources")
                .map(|path| path.join("runtime"));
            let (resource_root, resource_error) = match resource_result {
                Ok(path) => (Some(path), None),
                Err(error) => (None, Some(startup_error(&error))),
            };
            let shared: Arc<Mutex<Box<dyn RuntimeSupervisor>>> =
                Arc::new(Mutex::new(Box::new(UnavailableSupervisor {
                    error: "The bundled runtime is still being prepared.".into(),
                })));
            app.manage(DesktopState {
                supervisor: shared,
                resource_root,
                resource_error: resource_error.clone(),
                runtime_status: Mutex::new(RuntimeStatus {
                    message: if resource_error.is_some() {
                        "The bundled runtime could not start.".into()
                    } else {
                        "Preparing the local runtime…".into()
                    },
                    error: resource_error,
                }),
                startup_started: AtomicBool::new(false),
                startup_cancelled: AtomicBool::new(false),
                quitting: AtomicBool::new(false),
                updating: AtomicBool::new(false),
                drain_operation: AtomicBool::new(false),
                update_check_running: AtomicBool::new(false),
            });
            if let Err(error) = install_controlled_application_menu(app) {
                let state = app.state::<DesktopState>();
                state.startup_cancelled.store(true, Ordering::SeqCst);
                update_shell(
                    app.handle(),
                    &RuntimeStatus {
                        message: "OpsWitness could not install a safe Quit command.".into(),
                        error: Some(error.to_string()),
                    },
                );
                show_main(app.handle());
            }

            if let Err(error) = updater::register(app) {
                eprintln!("OpsWitness updater registration failed: {error:#}");
            }
            let tray_result: Result<()> = (|| {
                let show =
                    MenuItem::with_id(app, "show", "Show OpsWitness", true, None::<&str>)?;
                let update =
                    MenuItem::with_id(app, "update", "Check for Updates…", true, None::<&str>)?;
                let quit =
                    MenuItem::with_id(app, "quit", "Quit OpsWitness…", true, None::<&str>)?;
                let menu = Menu::with_items(app, &[&show, &update, &quit])?;
                let mut tray = TrayIconBuilder::with_id("opswitness")
                    .menu(&menu)
                    .show_menu_on_left_click(false)
                    .on_menu_event(|app, event| match event.id().as_ref() {
                        "show" => show_main(app),
                        "update" => updater::check_for_updates(app.clone(), true),
                        "quit" => request_quit(app),
                        _ => {}
                    })
                    .on_tray_icon_event(|tray, event| {
                        if let TrayIconEvent::Click {
                            button: MouseButton::Left,
                            button_state: MouseButtonState::Up,
                            ..
                        } = event
                        {
                            show_main(tray.app_handle());
                        }
                    });
                if let Some(icon) = app.default_window_icon() {
                    tray = tray.icon(icon.clone());
                }
                tray.build(app)?;
                Ok(())
            })();
            if let Err(error) = tray_result {
                eprintln!("OpsWitness tray setup failed: {error:#}");
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                let app = window.app_handle();
                let state = app.state::<DesktopState>();
                if !state.quitting.load(Ordering::SeqCst) {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .build(tauri::generate_context!());
    let application = match application {
        Ok(application) => application,
        Err(error) => {
            eprintln!("OpsWitness desktop initialization failed: {error:#}");
            MessageDialog::new()
                .set_level(MessageLevel::Error)
                .set_title("OpsWitness could not open")
                .set_description(
                    "The native App shell could not initialize. No Work or local data was \
                     changed. Restart this Mac and try again.",
                )
                .set_buttons(MessageButtons::Ok)
                .show();
            return;
        }
    };

    application.run(|app, event| match event {
        RunEvent::Ready => start_desktop_runtime(app),
        RunEvent::ExitRequested { api, .. } => {
            if let Some(state) = app.try_state::<DesktopState>() {
                if exit_requires_drain(
                    state.quitting.load(Ordering::SeqCst),
                    state.updating.load(Ordering::SeqCst),
                ) {
                    api.prevent_exit();
                    request_quit(app);
                }
            }
        }
        RunEvent::Exit => {
            if let Some(state) = app.try_state::<DesktopState>() {
                state.startup_cancelled.store(true, Ordering::SeqCst);
                if let Err(error) = stop_desktop_runtime(app) {
                    eprintln!(
                        "OpsWitness native-exit cleanup could not be fully confirmed: {error:#}"
                    );
                }
            }
        }
        _ => {}
    });
}

#[cfg(test)]
mod tests {
    use super::{
        exit_requires_drain, start_supervisor, startup_error, DrainStatus, RuntimeStatus,
        RuntimeSupervisor, UnavailableSupervisor,
    };
    use std::sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    };

    #[test]
    fn previous_build_conflict_has_recoverable_user_guidance() {
        let error =
            anyhow::anyhow!("previous desktop instance resource manifest identity does not match");
        let message = startup_error(&error);
        assert!(message.contains("previous version of OpsWitness"));
        assert!(message.contains("Restart this Mac"));
        assert!(message.contains("data and active Work untouched"));
    }

    #[test]
    fn unavailable_supervisor_fails_without_claiming_active_work() {
        let mut supervisor = UnavailableSupervisor {
            error: "safe startup refusal".into(),
        };
        let mut status = |_status: RuntimeStatus| {};
        assert!(supervisor.start(&mut status).is_err());
        assert!(matches!(
            supervisor.begin_draining().unwrap(),
            DrainStatus {
                active_work: false,
                backend_confirmed: false
            }
        ));
        supervisor.stop_all().unwrap();
    }

    struct StartFailureSupervisor {
        stopped: Arc<AtomicBool>,
    }

    impl RuntimeSupervisor for StartFailureSupervisor {
        fn start(&mut self, _status: &mut dyn FnMut(RuntimeStatus)) -> anyhow::Result<()> {
            anyhow::bail!("startup failed after spawning a child")
        }

        fn backend_url(&self) -> Option<&str> {
            None
        }

        fn begin_draining(&self) -> anyhow::Result<DrainStatus> {
            unreachable!()
        }

        fn cancel_draining(&self) -> anyhow::Result<()> {
            unreachable!()
        }

        fn stop_all(&mut self) -> anyhow::Result<()> {
            self.stopped.store(true, Ordering::SeqCst);
            Ok(())
        }
    }

    #[test]
    fn partial_start_failure_stops_owned_children() {
        let stopped = Arc::new(AtomicBool::new(false));
        let mut supervisor = StartFailureSupervisor {
            stopped: stopped.clone(),
        };
        let mut status = |_status: RuntimeStatus| {};

        assert!(start_supervisor(&mut supervisor, &mut status).is_err());
        assert!(stopped.load(Ordering::SeqCst));
    }

    #[test]
    fn every_external_exit_request_drains_unless_shutdown_is_already_owned() {
        assert!(exit_requires_drain(false, false));
        assert!(!exit_requires_drain(true, false));
        assert!(!exit_requires_drain(false, true));
        assert!(!exit_requires_drain(true, true));
    }
}
