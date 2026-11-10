//! Run the independent RTL verification suite; never substitute an e-class
//! membership check for proof. Missing tools and unproved assertions fail.
fn main() -> std::process::ExitCode {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap();
    match std::process::Command::new("python3")
        .arg(root.join("tools/validate.py"))
        .current_dir(root)
        .status()
    {
        Ok(status) if status.success() => std::process::ExitCode::SUCCESS,
        Ok(_) => std::process::ExitCode::FAILURE,
        Err(e) => {
            eprintln!("Cannot run RTL validation: {e}");
            std::process::ExitCode::FAILURE
        }
    }
}
