from repomgr.cli import RepomgrCli
from repomgr.config import Config


if __name__ == '__main__':
    cli = RepomgrCli()
    config = Config(cli)

