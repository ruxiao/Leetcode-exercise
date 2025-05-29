import subprocess
import os
import uuid
import shutil

# This should be consistent with the name cli.py places in the cloned repo,
# and also the name used in Dockerfile.python.template's COPY command.
CONTAINER_WRAPPER_SCRIPT_NAME_IN_BUILDER = "desci_container_wrapper.py"

# DEFAULT_PYTHON_DOCKERFILE_TEMPLATE = """...""" # Removed

def build_environment(repo_path, dependency_file_name, user_dockerfile_rel_path=None, image_tag_prefix="desci-verifier-env"):
    """
    Builds a Docker environment for the given repository.
    Returns the image tag on success, None on failure.
    """
    image_tag = f"{image_tag_prefix}:{uuid.uuid4()}" # Unique tag for each build

    dockerfile_to_use = ""
    generated_dockerfile_path = None # Store path if we generate it
    using_generated_dockerfile = False # Flag to know if we should clean it up (or keep for inspection)

    if user_dockerfile_rel_path:
        potential_dockerfile_abs_path = os.path.join(repo_path, user_dockerfile_rel_path)
        if os.path.exists(potential_dockerfile_abs_path):
            dockerfile_to_use = potential_dockerfile_abs_path
            print(f"Using user-provided Dockerfile: {dockerfile_to_use}")
        else:
            print(f"User-provided Dockerfile {potential_dockerfile_abs_path} not found. Attempting to generate one.")
    
    if not dockerfile_to_use:
        using_generated_dockerfile = True
        # Construct path to template relative to this script's location (src/)
        try:
            current_script_dir = os.path.dirname(__file__)
            # Go up one level from src/ to project root, then into templates/
            template_path = os.path.abspath(os.path.join(current_script_dir, "..", "templates", "Dockerfile.python.template"))
        except NameError: # __file__ not defined (e.g. in some interactive environments)
            print("Warning: __file__ not defined, template path might be incorrect if not run as script.")
            # Fallback assuming CWD is project root. This is less robust.
            template_path = os.path.join("templates", "Dockerfile.python.template")

        if not os.path.exists(template_path):
            print(f"Error: Dockerfile template not found at {template_path}")
            print(f"Current CWD for template search: {os.getcwd()}")
            # Check if src/templates/Dockerfile.python.template exists as a common misconfiguration
            alt_path = os.path.join("src", "templates", "Dockerfile.python.template")
            if os.path.exists(alt_path):
                print(f"Alternative path {alt_path} also checked.")
            return None

        try:
            with open(template_path, "r") as f_template:
                template_content = f_template.read()
        except IOError as e:
            print(f"Error reading Dockerfile template {template_path}: {e}")
            return None
        
        # Ensure the dependency file actually exists in the repo_path if we are generating a Dockerfile
        # as the template relies on it.
        if not dependency_file_name:
            print("Error: Dependency file name must be provided to generate Dockerfile from template.")
            return None
        abs_dependency_file_path = os.path.join(repo_path, dependency_file_name)
        if not os.path.exists(abs_dependency_file_path):
            print(f"Error: Dependency file '{abs_dependency_file_path}' not found in the repository path. Cannot generate Dockerfile.")
            return None

        # Also ensure the wrapper script (that cli.py should have placed) exists in repo_path,
        # as the template Dockerfile will try to COPY it.
        abs_wrapper_script_path = os.path.join(repo_path, CONTAINER_WRAPPER_SCRIPT_NAME_IN_BUILDER)
        if not os.path.exists(abs_wrapper_script_path):
            print(f"Error: Container wrapper script '{abs_wrapper_script_path}' not found in the repository path. cli.py should place this. Cannot generate Dockerfile.")
            return None

        generated_content = template_content.format(
            dependency_file=dependency_file_name, 
            container_wrapper_name=CONTAINER_WRAPPER_SCRIPT_NAME_IN_BUILDER
        )
        
        generated_dockerfile_path = os.path.join(repo_path, "Dockerfile.desci.generated") # Changed name
        try:
            with open(generated_dockerfile_path, "w") as f_gen:
                f_gen.write(generated_content)
            dockerfile_to_use = generated_dockerfile_path # Use the absolute path for -f arg later
            print(f"Generated Dockerfile at: {dockerfile_to_use} using template.")
        except IOError as e:
            print(f"Error writing generated Dockerfile: {e}")
            return None
    
    if not dockerfile_to_use:
        print("Error: No Dockerfile available (neither user-provided nor generated).")
        return None

    try:
        print(f"Building Docker image {image_tag} from context: {repo_path} using Dockerfile: {os.path.basename(dockerfile_to_use)}")
        
        # The -f argument to docker build needs the path to the Dockerfile.
        # If generated, dockerfile_to_use is an absolute path to a file at the root of the context.
        # If user-provided, dockerfile_to_use is also an absolute path (resolved earlier).
        # For docker build CLI, if -f path is within the context, it should be relative to context root.
        # os.path.basename(dockerfile_to_use) should work if the Dockerfile (user or generated)
        # is at the root of the build context (repo_path).
        dockerfile_for_build_command = os.path.basename(dockerfile_to_use)

        subprocess.run(
            ['docker', 'build', '-t', image_tag, '-f', dockerfile_for_build_command, '.'], # Context is cwd (repo_path)
            cwd=repo_path, 
            check=True,
            capture_output=True,
            text=True
        )
        print(f"Docker image {image_tag} built successfully.")
        return image_tag
    except subprocess.CalledProcessError as e:
        print(f"Error during Docker build: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return None
    except FileNotFoundError:
        print("Error: Docker command not found. Please ensure Docker is installed and running.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during build: {e}")
        return None
    finally:
            # If we used a generated dockerfile, and it still exists, print message.
            # No automatic removal for now, for easier debugging.
            if using_generated_dockerfile and generated_dockerfile_path and os.path.exists(generated_dockerfile_path):
                print(f"Generated Dockerfile {generated_dockerfile_path} was kept for inspection.")


if __name__ == '__main__':
    # This part requires a local Git repo and Docker running for testing.
    # Create a dummy repo for testing:
    # mkdir -p temp_test_repo/src
    # echo "print('Hello from script')" > temp_test_repo/src/main.py
    # echo "requests" > temp_test_repo/requirements.txt

    test_repo_base_dir = "temp_verifier_tests" # A base directory to hold test repos
    test_repo_dir = os.path.join(test_repo_base_dir, "test_project_simple")

    # Clean up previous test run if any
    if os.path.exists(test_repo_base_dir):
        shutil.rmtree(test_repo_base_dir)
    
    os.makedirs(os.path.join(test_repo_dir, "src")) # Create src subdirectory in test repo

    # Create a dummy requirements.txt
    with open(os.path.join(test_repo_dir, "requirements.txt"), "w") as f:
        f.write("numpy\nrequests") 
    # Create a dummy script file in src, though it's not directly run by build_environment
    with open(os.path.join(test_repo_dir, "src", "dummy_script.py"), "w") as f:
        f.write("print('hello from dummy script')")
    
    # CRITICAL: Create the dummy CONTAINER_WRAPPER_SCRIPT_NAME_IN_BUILDER file in the test repo root
    # because the new template Dockerfile will try to COPY it.
    with open(os.path.join(test_repo_dir, CONTAINER_WRAPPER_SCRIPT_NAME_IN_BUILDER), "w") as f:
        f.write("print('This is a dummy wrapper script for testing environment_builder')\nimport sys\nsys.exit(0)")


    print(f"Attempting to build environment for {test_repo_dir} (template generation path)...")
    tag = build_environment(test_repo_dir, "requirements.txt") # Test with generated Dockerfile
    if tag:
        print(f"Test build successful. Image tag: {tag}")
        # Here you might want to clean up the built image:
        try:
            print(f"Attempting to remove Docker image: {tag}")
            subprocess.run(['docker', 'rmi', tag], check=True, capture_output=True, text=True)
            print(f"Cleaned up Docker image: {tag}")
        except subprocess.CalledProcessError as e:
            print(f"Could not remove docker image {tag}. Error: {e.stderr}")
        except FileNotFoundError:
            print("Docker command not found, cannot remove image.")
    else:
        print("Test build failed.")
    
    # Test with a (non-existent) user Dockerfile to check generation path
    test_repo_user_df_nonexistent_dir = os.path.join(test_repo_base_dir, "test_project_user_df_nonexistent")
    os.makedirs(os.path.join(test_repo_user_df_nonexistent_dir, "src"))
    with open(os.path.join(test_repo_user_df_nonexistent_dir, "src", "dummy_script.py"), "w") as f:
        f.write("print('hello')")
    with open(os.path.join(test_repo_user_df_nonexistent_dir, "requirements.txt"), "w") as f:
        f.write("pandas")
    # CRITICAL: Also need the wrapper script in this test repo for generation to succeed
    with open(os.path.join(test_repo_user_df_nonexistent_dir, CONTAINER_WRAPPER_SCRIPT_NAME_IN_BUILDER), "w") as f:
        f.write("print('Dummy wrapper for non-existent user Dockerfile test')")

    print(f"\nAttempting to build environment for {test_repo_user_df_nonexistent_dir} with non-existent user Dockerfile (should generate)...")
    tag_user_df = build_environment(test_repo_user_df_nonexistent_dir, "requirements.txt", user_dockerfile_rel_path="mydockerfile.df")
    if tag_user_df:
        print(f"Test build with non-existent user Dockerfile (generation path) successful. Image tag: {tag_user_df}")
        try:
            subprocess.run(['docker', 'rmi', tag_user_df], check=True, capture_output=True, text=True)
            print(f"Cleaned up Docker image: {tag_user_df}")
        except subprocess.CalledProcessError as e:
            print(f"Could not remove docker image {tag_user_df}. Error: {e.stderr}")
        except FileNotFoundError:
            print("Docker command not found, cannot remove image.")
    else:
        print("Test build with non-existent user Dockerfile (generation path) failed.")

    # Test with an existing user Dockerfile
    test_repo_custom_df_dir = os.path.join(test_repo_base_dir, "test_project_custom_df")
    os.makedirs(os.path.join(test_repo_custom_df_dir, "src"))
    with open(os.path.join(test_repo_custom_df_dir, "src", "dummy_script.py"), "w") as f:
        f.write("print('hello from custom df script')")
    # For user-provided Dockerfile, requirements.txt might not be strictly needed by build_environment
    # if the Dockerfile itself doesn't reference it. But for consistency in test setup:
    with open(os.path.join(test_repo_custom_df_dir, "requirements.txt"), "w") as f: # May or may not be used by custom Dockerfile
        f.write("matplotlib")

    custom_dockerfile_content = f"""
FROM python:3.10-slim
WORKDIR /project
# This custom Dockerfile might or might not copy CONTAINER_WRAPPER_SCRIPT_NAME_IN_BUILDER.
# If it's essential for later execution steps, this could be a point of failure or require user guidance.
# For this test, we assume it's a valid Dockerfile that can build.
COPY requirements.txt . 
RUN pip install -r requirements.txt
COPY src/dummy_script.py .
CMD python ./dummy_script.py
"""
    # For this test, the custom Dockerfile does NOT copy the wrapper script.
    # This is fine for testing build_environment's ability to use a user's Dockerfile.
    # However, the CLI execution step would fail later if it relies on that wrapper being in the image.
    # This highlights a potential area for refinement in how the wrapper script is handled with custom Dockerfiles.

    with open(os.path.join(test_repo_custom_df_dir, "custom.Dockerfile"), "w") as f:
        f.write(custom_dockerfile_content)

    print(f"\nAttempting to build environment for {test_repo_custom_df_dir} with existing user Dockerfile...")
    # Provide dependency_file_name even if custom Dockerfile might not use it, as build_environment might try to check for it.
    tag_custom_df = build_environment(test_repo_custom_df_dir, "requirements.txt", user_dockerfile_rel_path="custom.Dockerfile")
    if tag_custom_df:
        print(f"Test build with existing user Dockerfile successful. Image tag: {tag_custom_df}")
        try:
            subprocess.run(['docker', 'rmi', tag_custom_df], check=True, capture_output=True, text=True)
            print(f"Cleaned up Docker image: {tag_custom_df}")
        except subprocess.CalledProcessError as e:
            print(f"Could not remove docker image {tag_custom_df}. Error: {e.stderr}")
        except FileNotFoundError:
            print("Docker command not found, cannot remove image.")
    else:
        print("Test build with existing user Dockerfile failed.")


    # Clean up all test directories
    if os.path.exists(test_repo_base_dir):
        shutil.rmtree(test_repo_base_dir) 
        print(f"\nCleaned up base test directory: {test_repo_base_dir}")
