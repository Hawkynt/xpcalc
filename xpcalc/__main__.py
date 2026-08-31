import sys

from .bittypes_ui import install
from .ui import main

install()

if __name__ == "__main__":
    sys.exit(main(sys.argv))
