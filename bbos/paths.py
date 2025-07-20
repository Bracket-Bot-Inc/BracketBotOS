from pathlib import Path
import bbos

BRACKETBOT_PATH = Path(bbos.__file__).parent.parent
APPS_PATH = BRACKETBOT_PATH / "apps"
BBOS_PATH = BRACKETBOT_PATH / "bbos"
AUTH_PTH = Path.home() / ".auth"
KEY_PTH = AUTH_PTH / "key.pem"
CERT_PTH = AUTH_PTH / "cert.pem"
