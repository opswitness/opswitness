use anyhow::{Context, Result};
use rfd::{MessageButtons, MessageDialog, MessageDialogResult, MessageLevel};
use std::sync::atomic::Ordering;
use std::time::Duration;
use tauri::{App, AppHandle, Manager};
use tauri_plugin_updater::UpdaterExt;
use url::Url;

use crate::{
    begin_desktop_drain, cancel_desktop_drain, finish_drain_operation, show_main,
    stop_desktop_runtime, try_begin_drain_operation, DesktopState,
};

const ALPHA_UPDATE_FEED: &str = "https://opswitness.com/updates/alpha/latest.json";

fn compiled_public_key() -> Option<&'static str> {
    option_env!("OPSWITNESS_UPDATER_PUBLIC_KEY").filter(|key| !key.trim().is_empty())
}

pub fn register(app: &mut App) -> Result<bool> {
    let Some(public_key) = compiled_public_key() else {
        return Ok(false);
    };
    app.handle()
        .plugin(
            tauri_plugin_updater::Builder::new()
                .pubkey(public_key)
                .build(),
        )
        .context("cannot register the signed Alpha updater")?;
    Ok(true)
}

pub fn check_for_updates(app: AppHandle, interactive: bool) {
    if compiled_public_key().is_none() {
        if interactive {
            MessageDialog::new()
                .set_level(MessageLevel::Info)
                .set_title("Updates are unavailable")
                .set_description(
                    "This ad-hoc build has no release updater key. Install a signed OpsWitness \
                     Alpha build to receive signed updates.",
                )
                .set_buttons(MessageButtons::Ok)
                .show();
        }
        return;
    }
    let state = app.state::<DesktopState>();
    if state.update_check_running.swap(true, Ordering::SeqCst) {
        return;
    }
    tauri::async_runtime::spawn(async move {
        let result = check_and_offer(app.clone(), interactive).await;
        app.state::<DesktopState>()
            .update_check_running
            .store(false, Ordering::SeqCst);
        if interactive {
            if let Err(error) = result {
                show_main(&app);
                MessageDialog::new()
                    .set_level(MessageLevel::Error)
                    .set_title("Update check failed")
                    .set_description(format!(
                        "OpsWitness could not verify the signed Alpha update feed.\n\n{error}"
                    ))
                    .set_buttons(MessageButtons::Ok)
                    .show();
            }
        }
    });
}

async fn check_and_offer(app: AppHandle, interactive: bool) -> Result<()> {
    let endpoint = Url::parse(ALPHA_UPDATE_FEED).context("invalid Alpha update feed URL")?;
    let update = app
        .updater_builder()
        .endpoints(vec![endpoint])?
        .timeout(Duration::from_secs(30))
        .build()?
        .check()
        .await?;
    let Some(update) = update else {
        if interactive {
            MessageDialog::new()
                .set_level(MessageLevel::Info)
                .set_title("OpsWitness is up to date")
                .set_description("No newer signed Alpha build is available.")
                .set_buttons(MessageButtons::Ok)
                .show();
        }
        return Ok(());
    };

    if !try_begin_drain_operation(&app) {
        return Ok(());
    }
    let drain = match begin_desktop_drain(&app) {
        Ok(status) => status,
        Err(error) => {
            finish_drain_operation(&app);
            return Err(error);
        }
    };
    if !drain.backend_confirmed {
        finish_drain_operation(&app);
        anyhow::bail!("the desktop backend did not confirm the update dispatch fence");
    }
    if drain.active_work {
        let cancel = cancel_desktop_drain(&app);
        finish_drain_operation(&app);
        cancel?;
        show_main(&app);
        MessageDialog::new()
            .set_level(MessageLevel::Warning)
            .set_title(format!("OpsWitness {} is available", update.version))
            .set_description(
                "Finish or stop the active Work before installing. OpsWitness will ask again \
                 after a later launch.",
            )
            .set_buttons(MessageButtons::Ok)
            .show();
        return Ok(());
    }
    let install = MessageDialog::new()
        .set_level(MessageLevel::Info)
        .set_title(format!("Install OpsWitness {}?", update.version))
        .set_description(
            "The update archive has a release signature. Choose Install to download and verify \
             it, or Later to keep this version.",
        )
        .set_buttons(MessageButtons::OkCancelCustom(
            "Install".into(),
            "Later".into(),
        ))
        .show()
        == MessageDialogResult::Ok;
    if !install {
        let cancel = cancel_desktop_drain(&app);
        finish_drain_operation(&app);
        cancel?;
        return Ok(());
    }

    let state = app.state::<DesktopState>();
    if state.updating.swap(true, Ordering::SeqCst) {
        let cancel = cancel_desktop_drain(&app);
        finish_drain_operation(&app);
        cancel?;
        return Ok(());
    }
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }

    let bytes = match update.download(|_, _| {}, || {}).await {
        Ok(bytes) => bytes,
        Err(error) => {
            app.state::<DesktopState>()
                .updating
                .store(false, Ordering::SeqCst);
            let cancel = cancel_desktop_drain(&app);
            finish_drain_operation(&app);
            show_main(&app);
            cancel?;
            return Err(error.into());
        }
    };

    let state = app.state::<DesktopState>();
    state.startup_cancelled.store(true, Ordering::SeqCst);
    state.quitting.store(true, Ordering::SeqCst);
    if let Err(error) = stop_desktop_runtime(&app) {
        state.quitting.store(false, Ordering::SeqCst);
        state.updating.store(false, Ordering::SeqCst);
        state.startup_cancelled.store(false, Ordering::SeqCst);
        let cancel = cancel_desktop_drain(&app);
        finish_drain_operation(&app);
        show_main(&app);
        cancel?;
        return Err(error.context(
            "the update was downloaded, but bundled-process shutdown could not be confirmed",
        ));
    }
    if let Err(error) = update.install(bytes) {
        MessageDialog::new()
            .set_level(MessageLevel::Error)
            .set_title("Update installation failed")
            .set_description(format!(
                "The signed update could not be installed. OpsWitness will restart the current \
                 version.\n\n{error}"
            ))
            .set_buttons(MessageButtons::Ok)
            .show();
    }
    app.restart();
}
