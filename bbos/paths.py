from pathlib import Path
import bbos

BRACKETBOT_PATH = Path(bbos.__file__).parent.parent
BBOS_PATH = BRACKETBOT_PATH / "bbos"
AUTH_PTH = Path.home() / ".auth"