import os
import inspect


def load_template(filename: str, templates_dir: str | None = None) -> str:
    if templates_dir is None:
        caller_file = inspect.stack()[1].filename
        caller_dir = os.path.dirname(os.path.abspath(caller_file))
        templates_dir = os.path.join(caller_dir, "templates")

    file_path = os.path.join(templates_dir, filename)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Template file not found: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()
