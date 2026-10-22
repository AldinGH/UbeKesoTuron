import datetime
import os
import shutil
import sys

import server


def main():
    if "--yes" not in sys.argv:
        print("This will erase ALL accounts, orders, loyalty cards, stock and logs.")
        if input("Type YES to continue: ").strip() != "YES":
            print("Cancelled. Nothing was changed.")
            return
    if os.path.exists(server.DATA_FILE):
        os.makedirs(server.BACKUP_DIR, exist_ok=True)
        keep = os.path.join(server.BACKUP_DIR, "data-{}-before-reset.json".format(datetime.date.today().isoformat()))
        shutil.copyfile(server.DATA_FILE, keep)
        print("Your old data was copied to", keep)
    for path in (server.DATA_FILE, server.DATA_FILE + ".bad", server.DATA_FILE + ".tmp"):
        if os.path.exists(path):
            os.remove(path)
    server.load()
    admin = next(u for u in server.DB["users"].values() if u["role"] == "admin")
    print("Done. The database is brand new.")
    print("Owner login:  {}  /  {}".format(admin["email"], server.ADMIN_PASSWORD))
    print("Start the app with: python run.py")


if __name__ == "__main__":
    main()
