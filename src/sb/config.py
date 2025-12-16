from pathlib import Path

from pydantic import BaseModel
import toml

config_path = Path.home() / ".config/sb/config.toml"

class ClientConfig(BaseModel):
    url: str
    username: str
    password: str

class Config(BaseModel):
    clients: dict[str, ClientConfig]

    @classmethod
    def load_from_file(cls):
        toml_config = toml.load(config_path)
        return cls(**toml_config)

  
if __name__ == "__main__":
    config = Config.load_from_file()
    print(config)
