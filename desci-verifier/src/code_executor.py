import subprocess
import os
import json # For structured output from the container
import shutil # For cleanup in main

# Helper script content to be run inside the container
# This script will run the user's script and then check for output files.
CONTAINER_WRAPPER_SCRIPT_NAME = "desci_container_wrapper.py"
CONTAINER_WRAPPER_SCRIPT_CONTENT = """
import subprocess
import os
import sys
import json

def main():
    user_script_path = sys.argv[1]
    expected_files_str = sys.argv[2] # A comma-separated string of file paths
    repo_root = os.getcwd() # Assumes WORKDIR is set correctly

    results = {
        "user_script_stdout": None,
        "user_script_stderr": None,
        "user_script_exit_code": None,
        "output_files_status": []
    }

    # 1. Execute the user's script
    # For simplicity, assuming python. Could be made more generic.
    command = ["python", user_script_path]
    try:
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        results["user_script_stdout"] = process.stdout
        results["user_script_stderr"] = process.stderr
        results["user_script_exit_code"] = process.returncode
    except Exception as e:
        results["user_script_stderr"] = f"Failed to even start user script: {str(e)}"
        results["user_script_exit_code"] = -99 # Arbitrary error code for wrapper failure
        print(json.dumps(results))
        sys.exit(1) # Wrapper script itself failed

    # 2. Check for expected output files if script execution seems okay (e.g. exit code 0)
    #    (or always check, depending on desired behavior)
    if results["user_script_exit_code"] == 0:
        if expected_files_str:
            expected_files_list = expected_files_str.split(',')
            for f_path_rel in expected_files_list:
                if not f_path_rel.strip(): # handle empty strings if any
                    continue
                f_path_abs = os.path.join(repo_root, f_path_rel.strip())
                found = os.path.exists(f_path_abs)
                results["output_files_status"].append({"file": f_path_rel.strip(), "found": found})
        else:
            # No expected files to check
            pass
    
    print(json.dumps(results)) # Output all results as a single JSON string

if __name__ == "__main__":
    main()
"""

def execute_code_in_docker(image_tag, run_script_path, expected_output_files=None, repo_root_in_container="/app"):
    """
    Executes the specified script inside a Docker container using a wrapper for result collection.
    Returns a dictionary with 'stdout', 'stderr', 'exit_code', 'output_files_status', and 'wrapper_error'.
    'run_script_path' and paths in 'expected_output_files' are relative to 'repo_root_in_container'.
    """
    final_results = {
        "stdout": None,          # stdout of the user script
        "stderr": None,          # stderr of the user script
        "exit_code": None,       # exit code of the user script
        "output_files_status": [], # list of {"file": "path", "found": True/False}
        "wrapper_error": None    # Errors from the wrapper/docker execution itself
    }
    
    if expected_output_files is None:
        expected_output_files = []

    # Convert list of expected files to a comma-separated string for the wrapper script argument
    expected_files_arg_str = ",".join(expected_output_files)

    # Command to run the wrapper script inside the container
    # The wrapper script then calls the user's script
    # Assumes CONTAINER_WRAPPER_SCRIPT_NAME is in the image's WORKDIR (e.g., /app)
    command_to_run_in_container = [
        "python", 
        CONTAINER_WRAPPER_SCRIPT_NAME,
        run_script_path,
        expected_files_arg_str
    ]
    
    try:
        print(f"Executing wrapper script for {run_script_path} in Docker image {image_tag} (WORKDIR: {repo_root_in_container})...")
        print(f"Expected output files to check: {expected_output_files}")

        process = subprocess.run(
            ['docker', 'run', 
             '--rm', # Keep it ephemeral
             '-w', repo_root_in_container, 
             image_tag] + command_to_run_in_container,
            capture_output=True,
            text=True,
            check=False 
        )

        # The wrapper script prints a JSON string to its stdout.
        # This JSON should be the last non-empty line of the output.
        if process.stdout: # Check if there's any stdout to parse
            json_output_str = None
            for line in reversed(process.stdout.strip().splitlines()):
                if line.strip(): # Find the last non-empty line
                    json_output_str = line
                    break
            
            if json_output_str:
                try:
                    parsed_output = json.loads(json_output_str)
                    final_results["stdout"] = parsed_output.get("user_script_stdout")
                    final_results["stderr"] = parsed_output.get("user_script_stderr")
                    final_results["exit_code"] = parsed_output.get("user_script_exit_code")
                    final_results["output_files_status"] = parsed_output.get("output_files_status", [])
                    
                    if final_results["exit_code"] == 0:
                        print(f"User script executed successfully. Exit code: {final_results['exit_code']}")
                    else:
                        # User script might have failed, but wrapper still provided JSON
                        print(f"User script execution finished with errors or did not run. User script exit code: {final_results['exit_code']}")
                        # Log stdout/stderr from user script if available
                        if final_results["stdout"]: print(f"User script stdout:\n{final_results['stdout']}")
                        if final_results["stderr"]: print(f"User script stderr:\n{final_results['stderr']}")


                except json.JSONDecodeError as e:
                    final_results["wrapper_error"] = f"Failed to parse JSON from wrapper. Error: {e}. Raw stdout: {process.stdout}"
                    final_results["stderr"] = process.stdout # Put all stdout in stderr if JSON parsing failed
                    final_results["exit_code"] = parsed_output.get("user_script_exit_code", -98) if 'parsed_output' in locals() else -98
            else:
                # No JSON output found, but there was stdout. Could be an error before JSON output.
                final_results["wrapper_error"] = "Wrapper script produced stdout, but no JSON found. Docker run may have failed or wrapper script error before JSON."
                final_results["stderr"] = process.stdout # Treat all stdout as error output from wrapper
                final_results["exit_code"] = -97 # Arbitrary code for this case
        
        # Handle cases where docker run itself failed or wrapper script had critical error (e.g., not found, python error in wrapper)
        if process.returncode != 0:
            # This is the exit code of `docker run` command itself.
            # If wrapper script exited with non-zero (e.g. `sys.exit(1)`), `docker run` still usually gives 0 if container ran.
            # This block is more for when `docker run` itself fails (e.g. image not found, command in container not found)
            # or if the wrapper script itself crashes hard (not just user script).
            msg = f"Docker run command failed with exit code {process.returncode}."
            print(msg)
            if not final_results["wrapper_error"]: # If no specific error already captured
                 final_results["wrapper_error"] = msg
            # If stderr from docker run is available and potentially more informative
            if process.stderr:
                print(f"Docker run stderr: {process.stderr}")
                if not final_results["stderr"]: # Don't overwrite user script stderr if already parsed
                    final_results["stderr"] = (final_results["stderr"] + "\n" + process.stderr) if final_results["stderr"] else process.stderr
            if final_results["exit_code"] is None: # If user script exit code wasn't parsed
                final_results["exit_code"] = -96 # Indicate docker run level failure.

        return final_results

    except FileNotFoundError:
        err_msg = "Error: Docker command not found. Please ensure Docker is installed and running."
        print(err_msg)
        final_results["wrapper_error"] = err_msg
        final_results["exit_code"] = -1 
        return final_results
    except Exception as e:
        err_msg = f"An unexpected error occurred in execute_code_in_docker: {e}"
        print(err_msg)
        final_results["wrapper_error"] = err_msg
        final_results["exit_code"] = -1
        return final_results

if __name__ == '__main__':
    test_image_tag = "desci-executor-test-v2:latest"
    sample_user_script_name = "user_script.py"
    test_context_dir = "temp_executor_test_v2"
    
    # Create necessary files for building the test image
    if os.path.exists(test_context_dir): # Clean up from previous run
        shutil.rmtree(test_context_dir)
    os.makedirs(test_context_dir)

    with open(os.path.join(test_context_dir, CONTAINER_WRAPPER_SCRIPT_NAME), "w") as f:
        f.write(CONTAINER_WRAPPER_SCRIPT_CONTENT)

    user_script_content_success = """
import os
import sys
print('User script stdout: Processed data.')
print('User script stderr: Minor warning.', file=sys.stderr)
os.makedirs('results', exist_ok=True)
with open('results/output1.txt', 'w') as f: f.write('Output 1 content')
with open('output2.csv', 'w') as f: f.write('col1,col2\\nval1,val2')
sys.exit(0)
"""
    with open(os.path.join(test_context_dir, sample_user_script_name), "w") as f:
        f.write(user_script_content_success)

    user_script_content_failure = """
import sys
print('User script stdout: Starting process...')
print('User script stderr: A critical error occurred!', file=sys.stderr)
sys.exit(1)
"""
    with open(os.path.join(test_context_dir, "failing_user_script.py"), "w") as f:
        f.write(user_script_content_failure)

    user_script_empty_output = """
import sys
# This script produces no stdout/stderr and exits.
sys.exit(0)
"""
    with open(os.path.join(test_context_dir, "empty_output_script.py"), "w") as f:
        f.write(user_script_empty_output)


    # Dockerfile for the test image
    test_dockerfile_content = f"""
FROM python:3.9-slim
WORKDIR /app
COPY {CONTAINER_WRAPPER_SCRIPT_NAME} .
COPY {sample_user_script_name} .
COPY failing_user_script.py .
COPY empty_output_script.py .
# RUN pip install --no-cache-dir requests # Example, not needed for these scripts
"""
    with open(os.path.join(test_context_dir, "Dockerfile.test"), "w") as f:
        f.write(test_dockerfile_content)

    build_success = False
    print(f"Building test image {test_image_tag}...")
    try:
        build_process = subprocess.run(
            ['docker', 'build', '-t', test_image_tag, '-f', 'Dockerfile.test', '.'],
            cwd=test_context_dir,
            check=True, capture_output=True, text=True
        )
        print(f"Test image {test_image_tag} built successfully.")
        build_success = True
    except FileNotFoundError:
        print("Docker command not found. Skipping advanced executor test.")
    except subprocess.CalledProcessError as e:
        print(f"Error building test Docker image for executor: {e}")
        print(f"Build command: {' '.join(e.cmd)}")
        print(f"Stderr: {e.stderr}")
        print(f"Stdout: {e.stdout}")
    except Exception as e:
        print(f"An unexpected error occurred during test setup (image build): {e}")

    if build_success:
        # Test 1: Successful execution, files found/not found
        print("\n--- Test 1: Successful execution, mixed file findings ---")
        expected_files_1 = ["results/output1.txt", "output2.csv", "non_existent_file.log"]
        results_1 = execute_code_in_docker(test_image_tag, sample_user_script_name, expected_files_1)
        print("Execution Results 1 (JSON):", json.dumps(results_1, indent=2))
        assert results_1["exit_code"] == 0, f"Test 1: Expected exit code 0, got {results_1['exit_code']}"
        assert "User script stdout: Processed data." in results_1["stdout"], "Test 1: Stdout mismatch"
        assert "User script stderr: Minor warning." in results_1["stderr"], "Test 1: Stderr mismatch"
        assert results_1["output_files_status"][0]["file"] == "results/output1.txt" and results_1["output_files_status"][0]["found"] == True, "Test 1: File 1 status error"
        assert results_1["output_files_status"][1]["file"] == "output2.csv" and results_1["output_files_status"][1]["found"] == True, "Test 1: File 2 status error"
        assert results_1["output_files_status"][2]["file"] == "non_existent_file.log" and results_1["output_files_status"][2]["found"] == False, "Test 1: File 3 status error"
        assert results_1["wrapper_error"] is None, f"Test 1: Expected no wrapper error, got {results_1['wrapper_error']}"


        # Test 2: Script fails, file checks should ideally not run or be empty
        print("\n--- Test 2: Script fails ---")
        results_2 = execute_code_in_docker(test_image_tag, "failing_user_script.py", ["results/output1.txt"])
        print("Execution Results 2 (JSON):", json.dumps(results_2, indent=2))
        assert results_2["exit_code"] == 1, f"Test 2: Expected exit code 1, got {results_2['exit_code']}"
        assert "User script stdout: Starting process..." in results_2["stdout"], "Test 2: Stdout mismatch"
        assert "User script stderr: A critical error occurred!" in results_2["stderr"], "Test 2: Stderr mismatch"
        # Current wrapper logic: output_files_status is empty if user_script_exit_code != 0
        assert not results_2["output_files_status"], f"Test 2: Expected empty output_files_status, got {results_2['output_files_status']}"
        assert results_2["wrapper_error"] is None, f"Test 2: Expected no wrapper error, got {results_2['wrapper_error']}"

        # Test 3: Script runs successfully but no files expected
        print("\n--- Test 3: Successful execution, no files expected ---")
        results_3 = execute_code_in_docker(test_image_tag, sample_user_script_name, []) # Empty list
        print("Execution Results 3 (JSON):", json.dumps(results_3, indent=2))
        assert results_3["exit_code"] == 0
        assert not results_3["output_files_status"] # Should be empty

        # Test 4: Script runs successfully, expected_output_files is None
        print("\n--- Test 4: Successful execution, expected_output_files is None ---")
        results_4 = execute_code_in_docker(test_image_tag, sample_user_script_name, None) # None
        print("Execution Results 4 (JSON):", json.dumps(results_4, indent=2))
        assert results_4["exit_code"] == 0
        assert not results_4["output_files_status"] # Should be empty
        
        # Test 5: User script produces no stdout/stderr
        print("\n--- Test 5: User script with no stdout/stderr ---")
        results_5 = execute_code_in_docker(test_image_tag, "empty_output_script.py", [])
        print("Execution Results 5 (JSON):", json.dumps(results_5, indent=2))
        assert results_5["exit_code"] == 0, f"Test 5: Expected exit code 0, got {results_5['exit_code']}"
        assert results_5["stdout"] == "", f"Test 5: Expected empty stdout, got '{results_5['stdout']}'"
        assert results_5["stderr"] == "", f"Test 5: Expected empty stderr, got '{results_5['stderr']}'"
        assert not results_5["output_files_status"], "Test 5: Expected empty file status"
        assert results_5["wrapper_error"] is None, f"Test 5: Expected no wrapper error, got {results_5['wrapper_error']}"


    # Cleanup
    print("\nStarting cleanup phase...")
    try:
        print(f"Attempting to remove test image {test_image_tag}...")
        img_remove_result = subprocess.run(['docker', 'rmi', test_image_tag], capture_output=True, text=True, check=False)
        if img_remove_result.returncode == 0:
            print(f"Successfully removed test image {test_image_tag}.")
        else:
            print(f"Could not remove test image {test_image_tag}. It might not exist or be in use. Stderr: {img_remove_result.stderr.strip()}")
            
    except FileNotFoundError:
        print("Docker command not found, cannot remove test image.")
    except Exception as e:
        print(f"An unexpected error occurred during image cleanup: {e}")
    finally:
        if os.path.exists(test_context_dir):
            shutil.rmtree(test_context_dir)
            print(f"Cleaned up test directory: {test_context_dir}")
        print("Executor (with result capture) test finished.")
