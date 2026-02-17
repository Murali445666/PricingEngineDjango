import sys
import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

try:
    print(f"django: {django.get_version()}")
    import django.contrib
    print("django.contrib imported successfully")
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")

try:
    import rest_framework
    print(f"rest_framework: {rest_framework.__version__}")
    from rest_framework import views
    print("rest_framework.views imported successfully")
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")

print(f"Executable: {sys.executable}")
# print(f"Path: {sys.path}") # Commenting out path to reduce noise, unless needed

try:
    import core.models
    print("core.models imported successfully")
except ImportError as e:
    print(f"ImportError (core.models): {e}")
except Exception as e:
    print(f"Error (core.models): {e}")
