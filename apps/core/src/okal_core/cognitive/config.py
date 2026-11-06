"""Owner-local configuration, never supplied by chat or model output."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat

from .providers import ModelPin


@dataclass(frozen=True)
class AdapterConfig:
    python: Path
    llm: ModelPin
    embedding: ModelPin
    dimensions: int
    embedding_gpu: bool = False

    @classmethod
    def read(cls, path: Path):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_size > 8192):
                raise ValueError('memory_config_must_be_owner_private')
            with os.fdopen(fd, 'r', encoding='utf-8', closefd=False) as stream:
                data = json.load(stream)
        finally:
            os.close(fd)
        if (not isinstance(data, dict) or set(data) != {
                'version', 'local_only_confirmed', 'python', 'llm',
                'embedding', 'dimensions', 'embedding_gpu'}
                or type(data['version']) is not int or data['version'] != 1
                or data['local_only_confirmed'] is not True
                or type(data['embedding_gpu']) is not bool
                or type(data['dimensions']) is not int or not 64 <= data['dimensions'] <= 4096):
            raise ValueError('invalid_local_memory_config')
        python = Path(data['python'])
        if not python.is_absolute() or not python.is_file() or not os.access(python, os.X_OK):
            raise ValueError('memory_python_must_be_explicit_executable')
        executable = python.stat()
        if executable.st_uid not in {0, os.getuid()} or executable.st_mode & 0o022:
            raise ValueError('unsafe_memory_python_permissions')
        pins = []
        for value in (data['llm'], data['embedding']):
            if not isinstance(value, dict) or set(value) != {'name', 'digest'}:
                raise ValueError('invalid_local_model_pin')
            pins.append(ModelPin(**value))
        return cls(python, *pins, data['dimensions'], data['embedding_gpu'])
