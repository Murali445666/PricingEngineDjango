import pymysql

# 1. Install PyMySQL as the MySQL driver
pymysql.install_as_MySQLdb()

# 2. Monkey-patch the version to fool Django
# Django requires mysqlclient 2.2.1+. PyMySQL usually reports 1.4.6.
# We manually overwrite the version info in the imported module.
import MySQLdb
if not hasattr(MySQLdb, 'version_info'):
    MySQLdb.version_info = (2, 2, 2, 'final', 0)
else:
    # Force it to be a tuple > (2, 2, 1)
    MySQLdb.version_info = (2, 2, 2, 'final', 0)