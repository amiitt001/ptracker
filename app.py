import os
import sys

# Ensure backend directory is in the import path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend'))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Remove the root 'app' from sys.modules to avoid circular/self-import
# when importing the actual backend 'app' module
if 'app' in sys.modules:
    del sys.modules['app']

import app as backend_app
app = backend_app.app
