import subprocess
import os
import shutil

def clone_repo(git_url, target_dir, branch=None):
    """
    Clones a Git repository into the target_dir.
    If a branch is specified, it checks out that branch.
    Returns True on success, False on failure.
    """
    if os.path.exists(target_dir):
        print(f"Target directory {target_dir} already exists. Removing it.")
        shutil.rmtree(target_dir) # Or handle differently, e.g., by naming uniquely
    
    os.makedirs(target_dir, exist_ok=True)

    try:
        print(f"Cloning repository: {git_url} into {target_dir}")
        subprocess.run(['git', 'clone', git_url, target_dir], check=True, capture_output=True, text=True)
        print("Repository cloned successfully.")

        if branch:
            print(f"Checking out branch: {branch}")
            subprocess.run(['git', '-C', target_dir, 'checkout', branch], check=True, capture_output=True, text=True)
            print(f"Successfully checked out branch: {branch}")
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error during git operation: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False
    except FileNotFoundError:
        print("Error: Git command not found. Please ensure Git is installed and in your PATH.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False

if __name__ == '__main__':
    # Example usage (optional, for direct testing of the script)
    test_repo_url = "https://github.com/git-guides/install-git.git" # A small public repo for testing
    test_target_dir = "temp_repo_clone"
    test_branch = None # or a specific branch if the test repo has one.

    print(f"Starting clone test for {test_repo_url}")
    if clone_repo(test_repo_url, test_target_dir, branch=test_branch):
        print(f"Test clone successful into {test_target_dir}")
        # Clean up the test clone
        # shutil.rmtree(test_target_dir)
        # print(f"Cleaned up {test_target_dir}")
    else:
        print("Test clone failed.")
    
    # Example with a branch (if you have a test repo with a specific branch)
    # test_repo_with_branch = "YOUR_TEST_REPO_URL_WITH_BRANCHES"
    # test_specific_branch = "YOUR_BRANCH_NAME"
    # test_target_dir_branch = "temp_repo_clone_branch"
    # if clone_repo(test_repo_with_branch, test_target_dir_branch, branch=test_specific_branch):
    #     print(f"Test clone with branch successful into {test_target_dir_branch}")
    # else:
    #     print("Test clone with branch failed.")
