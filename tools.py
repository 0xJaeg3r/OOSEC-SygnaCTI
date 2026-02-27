import subprocess
from agno.tools import tool


# ------- CLI Tools -------

@tool
def echo(text: str, args: str = "") -> str:
    """Output text to stdout, optionally piping through other commands.

    Executes: echo {text} {args}

    Args:
        text (str): The text to output.
        args (str): Additional arguments or pipe commands (e.g., "| grep pattern", "| base64").

    Returns:
        str: The echoed text or processed output.
    """
    command = f"echo {text} {args}"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return f"Error running echo:\n{result.stderr.strip()}"
        return result.stdout.strip()
    except Exception as e:
        return f"Error running echo: {str(e)}"


@tool
def pipe(command: str) -> str:
    """Execute a piped shell command.

    Executes: {command}

    Args:
        command (str): The full command with pipes (e.g., "cat file.txt | grep pattern | sort -u").

    Returns:
        str: Command output.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode != 0:
            return f"Error running command:\n{result.stderr.strip()}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 300 seconds"
    except Exception as e:
        return f"Error running command: {str(e)}"


@tool
def list_dir(path: str, args: str = "") -> str:
    """List the contents of a directory.

    Args:
        path (str): The directory path to list.
        args (str): Additional ls flags (e.g., "-la", "-lh").

    Returns:
        str: Directory listing output.
    """
    command = f"ls {path} {args}"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return f"Error listing directory:\n{result.stderr.strip()}"
        return result.stdout.strip()
    except Exception as e:
        return f"Error running ls: {str(e)}"


@tool
def cat_file(file_path: str, args: str = "") -> str:
    """Display the contents of a file, optionally piping through other commands.

    Args:
        file_path (str): The path to the file to read.
        args (str): Additional arguments or pipe commands (e.g., "| grep pattern", "| jq .data").

    Returns:
        str: File contents or processed output.
    """
    command = f"cat {file_path} {args}"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return f"Error reading file:\n{result.stderr.strip()}"
        return result.stdout.strip()
    except Exception as e:
        return f"Error running cat: {str(e)}"


@tool
def pwd_command() -> str:
    """Retrieve the current working directory.

    Returns:
        str: The current working directory path.
    """
    try:
        result = subprocess.run(
            "pwd",
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return f"Error running pwd:\n{result.stderr.strip()}"
        return result.stdout.strip()
    except Exception as e:
        return f"Error running pwd: {str(e)}"


@tool
def find_file(file_path: str, args: str = "") -> str:
    """Find files in the filesystem.

    Args:
        file_path (str): The starting directory path for the search.
        args (str): Additional find arguments (e.g., "-name '*.json'", "-type f").

    Returns:
        str: List of matching file paths.
    """
    command = f"find {file_path} {args}"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return f"Error running find:\n{result.stderr.strip()}"
        return result.stdout.strip()
    except Exception as e:
        return f"Error running find: {str(e)}"
    


#-----Telegram search tools -----
try:
    from telegram_search_tool import get_telegram_search_tools
    TELEGRAM_SEARCH_TOOLS = get_telegram_search_tools()
except ImportError:
    TELEGRAM_SEARCH_TOOLS = []

#-----Dark web search tool ------

try:
    from dark_web_search_tool import get_dark_web_search_tools
    DARK_WEB_SEARCH_TOOLS = get_dark_web_search_tools()
except ImportError:
    DARK_WEB_SEARCH_TOOLS = []


CTI_TOOLS = [
    #System and file operations
    echo,
    pipe,
    list_dir,
    cat_file,
    pwd_command,
    find_file,
] + TELEGRAM_SEARCH_TOOLS + DARK_WEB_SEARCH_TOOLS