"""Provides utility functions for file and directory operations."""

import os
import pathlib
import shutil
import typing
from dataclasses import dataclass

from platformdirs import PlatformDirs

from brokenspoke_analyzer.core import constant


@dataclass
class BaseResult:
    """Base result class with common fields for deletion operations."""

    file_count: int
    directory_count: int
    total_item_count: int
    space_bytes: int
    space_gb: float
    errors: typing.List[str]
    folder_path: str


@dataclass
class DeletionResult(BaseResult):
    """Result of a folder deletion operation."""


@dataclass
class DryRunResult(BaseResult):
    """Result of a dry run deletion preview."""

    files_list: typing.List[str]
    directories_list: typing.List[str]
    dry_run: bool = True


def get_size(path: pathlib.Path) -> int:
    """
    Calculate the total size of a file or directory in bytes.

    Returns the size in bytes.

    Example:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as td:
        >>>     d = pathlib.Path(td)
        >>>     assert get_size(d) == 0
        >>>     f = d / "test.txt"
        >>>     f.write_text('Hello test!')
        >>>     assert get_size(f) == 11
    """
    if path.is_file():
        try:
            return path.stat().st_size
        except (OSError, FileNotFoundError):
            return 0
    elif path.is_dir():
        total_size: int = 0
        try:
            item: pathlib.Path
            for item in path.rglob("*"):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                    except (OSError, FileNotFoundError):
                        continue
        except (OSError, PermissionError):
            pass
        return total_size
    return 0


def bytes_to_gb(bytes_size: int) -> float:
    """
    Convert bytes to gigabytes.

    Returns the size in GB rounded to 3 decimal places.

    Examples:
        >>> bytes_to_gb(1024**3)
        1.0
        >>> bytes_to_gb(552_599_552)
        0.515
    """
    return round(bytes_size / (1024**3), 3)


def delete_folder_contents_safe(
    folder_path: pathlib.Path,
    include_hidden: bool = False,
    dry_run: bool = False,
) -> typing.Union[DryRunResult, DeletionResult]:
    """
    Safe version of delete_folder_contents with dry run option.

    Args:
        folder_path: Path to the folder to clear
        include_hidden: Whether to delete hidden items (starting with '.')
        dry_run: If True, only show what would be deleted without actually deleting

    Returns:
        Summary with counts of items to be deleted/deleted, space to be reclaimed, and any errors
    """
    folder_path_obj = pathlib.Path(folder_path)

    # Check if folder exists
    if not folder_path_obj.exists():
        raise FileNotFoundError(f"Folder '{folder_path_obj}' does not exist")

    if not folder_path_obj.is_dir():
        raise ValueError(f"'{folder_path_obj}' is not a directory")

    files_to_delete: typing.List[typing.Tuple[pathlib.Path, int]] = []
    dirs_to_delete: typing.List[typing.Tuple[pathlib.Path, int]] = []
    total_size_to_reclaim: int = 0
    errors: typing.List[str] = []

    try:
        # First, collect all items to be deleted and calculate total size
        item: pathlib.Path
        for item in folder_path_obj.iterdir():
            # Skip hidden items if include_hidden is False
            if not include_hidden and item.name.startswith("."):
                continue

            item_size: int = get_size(item)
            total_size_to_reclaim += item_size

            if item.is_file():
                files_to_delete.append((item, item_size))
            elif item.is_dir():
                dirs_to_delete.append((item, item_size))

        space_to_reclaim_gb: float = bytes_to_gb(total_size_to_reclaim)

        if dry_run:
            file_path: pathlib.Path
            size: int
            dir_path: pathlib.Path

            return DryRunResult(
                file_count=len(files_to_delete),
                directory_count=len(dirs_to_delete),
                total_item_count=len(files_to_delete) + len(dirs_to_delete),
                space_bytes=total_size_to_reclaim,
                space_gb=space_to_reclaim_gb,
                files_list=[str(f[0]) for f in files_to_delete],
                directories_list=[str(d[0]) for d in dirs_to_delete],
                errors=[],
                folder_path=str(folder_path_obj),
                dry_run=True,
            )

        # Actually delete the items
        deleted_files: int = 0
        deleted_dirs: int = 0
        actual_size_reclaimed: int = 0

        # Delete files
        for file_path, size in files_to_delete:
            try:
                file_path.unlink()
                deleted_files += 1
                actual_size_reclaimed += size
            except PermissionError as e:
                error_msg: str = f"Permission denied: {file_path} - {e}"
                errors.append(error_msg)
            except Exception as e:
                error_msg = f"Failed to delete {file_path}: {e}"
                errors.append(error_msg)

        # Delete directories
        for dir_path, size in dirs_to_delete:
            try:
                shutil.rmtree(dir_path)
                deleted_dirs += 1
                actual_size_reclaimed += size
            except PermissionError as e:
                error_msg = f"Permission denied: {dir_path} - {e}"
                errors.append(error_msg)
            except Exception as e:
                error_msg = f"Failed to delete {dir_path}: {e}"
                errors.append(error_msg)

        actual_space_reclaimed_gb: float = bytes_to_gb(actual_size_reclaimed)

        return DeletionResult(
            file_count=deleted_files,
            directory_count=deleted_dirs,
            total_item_count=deleted_files + deleted_dirs,
            space_bytes=actual_size_reclaimed,
            space_gb=actual_space_reclaimed_gb,
            errors=errors,
            folder_path=str(folder_path_obj),
        )

    except PermissionError as e:
        raise PermissionError(
            f"Permission denied accessing folder '{folder_path_obj}': {e}"
        )


def get_user_cache_dir(ensure_exists: bool = True) -> pathlib.Path:
    """Return the user cache directory."""
    dirs = PlatformDirs(
        constant.APPNAME, constant.APPAUTHOR, ensure_exists=ensure_exists
    )
    return pathlib.Path(dirs.user_cache_dir)
