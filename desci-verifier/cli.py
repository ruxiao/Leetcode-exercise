import argparse
import json
import os
import shutil
import sys
import subprocess # Added for potential docker rmi in future cleanup

# Add src to Python path to allow direct import of modules
# This assumes cli.py is in the root of the desci-verifier project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

try:
    from repository_cloner import clone_repo
    from environment_builder import build_environment
    # Import the necessary content for the wrapper script from code_executor
    from code_executor import execute_code_in_docker, CONTAINER_WRAPPER_SCRIPT_NAME, CONTAINER_WRAPPER_SCRIPT_CONTENT
except ImportError as e:
    print(f"Error importing modules: {e}. Ensure you are in the project root or have set PYTHONPATH correctly.")
    print(f"Current sys.path: {sys.path}")
    # Also list files in src to help debug if running in an unexpected environment
    src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'src'))
    if os.path.exists(src_path):
        print(f"Contents of {src_path}: {os.listdir(src_path)}")
    else:
        print(f"{src_path} does not exist.")
    sys.exit(1)

TEMP_CLONE_DIR = "temp_repo_clone_cli" # Define at module level for cleanup_and_exit

def main():
    parser = argparse.ArgumentParser(description="DeSci Verifier CLI - MVP")
    parser.add_argument("config_file", help="Path to the JSON configuration file for verification.")
    args = parser.parse_args()

    if not os.path.exists(args.config_file):
        print(f"Error: Configuration file not found at {args.config_file}")
        sys.exit(1)

    try:
        with open(args.config_file, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: Could not parse JSON configuration file: {args.config_file}")
        sys.exit(1)
    except IOError:
        print(f"Error: Could not read configuration file: {args.config_file}")
        sys.exit(1)

    # --- 1. Clone Repository ---
    print(f"\n--- Step 1: Cloning Repository ---")
    git_url = config.get("git_url")
    branch = config.get("branch") # Optional
    if not git_url:
        print("Error: 'git_url' not specified in config.")
        sys.exit(1)

    if os.path.exists(TEMP_CLONE_DIR):
        print(f"Temporary clone directory {TEMP_CLONE_DIR} exists. Removing it first.")
        try:
            shutil.rmtree(TEMP_CLONE_DIR)
        except Exception as e:
            print(f"Warning: Could not remove existing {TEMP_CLONE_DIR}: {e}")
            # Depending on the error, might be fatal, but clone_repo might handle it too.

    print(f"Cloning {git_url} (branch: {branch or 'default'}) into {TEMP_CLONE_DIR}...")
    if not clone_repo(git_url, TEMP_CLONE_DIR, branch=branch):
        print("Failed to clone repository.")
        cleanup_and_exit(1, None) # Pass None for image_tag as it's not created yet
    print("Repository cloned successfully.")

    # --- Temporary measure for CONTAINER_WRAPPER_SCRIPT ---
    # This script needs to be inside the build context (cloned repo)
    # for Docker to COPY it into the image.
    # environment_builder.py will be updated later to manage this better,
    # possibly by taking the script content directly or having a fixed template path.
    wrapper_script_path_in_clone = os.path.join(TEMP_CLONE_DIR, CONTAINER_WRAPPER_SCRIPT_NAME)
    try:
        with open(wrapper_script_path_in_clone, "w") as f:
            f.write(CONTAINER_WRAPPER_SCRIPT_CONTENT)
        print(f"Placed '{CONTAINER_WRAPPER_SCRIPT_NAME}' in cloned repo root for image build.")
    except IOError as e:
        print(f"Critical Error: Could not write {CONTAINER_WRAPPER_SCRIPT_NAME} to {TEMP_CLONE_DIR}: {e}")
        cleanup_and_exit(1, None)
    # --- End temporary measure ---

    # --- 2. Build Environment ---
    print(f"\n--- Step 2: Building Docker Environment ---")
    dependency_file = config.get("dependency_file")
    user_dockerfile_rel_path = config.get("dockerfile") # Optional, relative to repo root

    # Critical check: if user provides a Dockerfile, dependency_file might be optional for build_environment
    # but our current build_environment generates one if user_dockerfile_rel_path is None or not found,
    # and that generation *requires* dependency_file_name.
    if not dependency_file and not user_dockerfile_rel_path:
        print("Error: Either 'dependency_file' (for generated Dockerfile) or 'dockerfile' (user-provided) must be specified in config.")
        cleanup_and_exit(1, None)
    
    print(f"Building environment from context: {TEMP_CLONE_DIR}")
    print(f"  Dependency file specified: {dependency_file}")
    print(f"  User Dockerfile specified: {user_dockerfile_rel_path}")

    image_tag = build_environment(
        repo_path=TEMP_CLONE_DIR,
        dependency_file_name=dependency_file, 
        user_dockerfile_rel_path=user_dockerfile_rel_path
    )

    if not image_tag:
        print("Failed to build Docker environment.")
        cleanup_and_exit(1, None) # image_tag is None here
    print(f"Docker environment built successfully. Image tag: {image_tag}")

    # --- 3. Execute Code ---
    print(f"\n--- Step 3: Executing Code ---")
    run_script = config.get("run_script")
    expected_outputs = config.get("expected_output_files", []) # Default to empty list

    if not run_script:
        print("Error: 'run_script' not specified in config.")
        cleanup_and_exit(1, image_tag) # Pass image_tag for potential cleanup

    print(f"Executing script '{run_script}' in image '{image_tag}'...")
    print(f"Expected output files: {expected_outputs}")
    
    execution_results = execute_code_in_docker(
        image_tag=image_tag,
        run_script_path=run_script, 
        expected_output_files=expected_outputs,
        # repo_root_in_container="/app" # Assuming default from execute_code_in_docker
    )

    print("\n--- Step 4: Verification Results ---")
    # Overall success indication (can be refined)
    final_success = True

    if execution_results.get("wrapper_error"):
        print(f"!! Execution Error from Wrapper: {execution_results['wrapper_error']}")
        final_success = False
    
    user_script_exit_code = execution_results.get('exit_code')
    print(f"User Script Exit Code: {user_script_exit_code}")
    if user_script_exit_code != 0:
        final_success = False
        print("  (Note: User script non-zero exit code indicates an issue.)")

    print(f"\nUser Script Stdout:")
    print(execution_results.get('stdout', '(empty)'))
    print(f"\nUser Script Stderr:")
    print(execution_results.get('stderr', '(empty)'))

    print("\nExpected Output Files Status:")
    if execution_results.get("output_files_status"):
        all_files_found = True
        for item in execution_results["output_files_status"]:
            print(f"  - File: {item['file']}, Found: {item['found']}")
            if not item['found']:
                all_files_found = False
        if not all_files_found:
            final_success = False
            print("  (Note: Not all expected output files were found.)")
        if not expected_outputs: # List was provided but empty
             print("  (No expected output files were listed to check.)")
    elif expected_outputs: # Files were expected but status is missing/empty (problem)
        print("  (Warning: Expected output files were specified, but no status was returned from executor.)")
        final_success = False
    else: # No files were expected, and none checked.
        print("  (No expected output files were specified to check.)")
    
    print("\n--- Summary ---")
    if final_success:
        print("Verification Succeeded (script ran, exit code 0, all expected files found if any).")
    else:
        print("Verification Failed (see errors or missing files above).")

    # --- 5. Cleanup ---
    # For now, we always keep the Docker image for inspection.
    # Manual cleanup command will be suggested to the user.
    print(f"\n--- Step 5: Cleanup ---")
    print(f"Keeping Docker image '{image_tag}' for inspection.")
    print(f"To remove it manually: docker rmi {image_tag}")
    
    cleanup_and_exit(0 if final_success else 1, image_tag, always_rm_clone_dir=True)


def cleanup_and_exit(status_code, image_tag_to_potentially_remove, always_rm_clone_dir=True):
    # `image_tag_to_potentially_remove` is kept for future use if we decide to auto-remove images.
    if always_rm_clone_dir and os.path.exists(TEMP_CLONE_DIR):
        try:
            shutil.rmtree(TEMP_CLONE_DIR)
            print(f"Cleaned up temporary clone directory: {TEMP_CLONE_DIR}")
        except Exception as e:
            print(f"Warning: Failed to remove temporary directory {TEMP_CLONE_DIR}: {e}")
    
    if status_code == 0:
        print("\nDeSci Verifier finished successfully.")
    else:
        print("\nDeSci Verifier finished with errors.")
    sys.exit(status_code)

if __name__ == "__main__":
    main()
