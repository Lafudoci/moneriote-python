import os
import tempfile
from multiprocessing import freeze_support

freeze_support()

PATH_CACHE = os.path.join(tempfile.gettempdir(), 'moneriote-cache.json')
CONFIG = {}
