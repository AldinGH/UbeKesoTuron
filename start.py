import os

import server


def main():
    server.load()
    port = int(os.environ.get("PORT", "8000"))
    httpd = server.Server(("0.0.0.0", port), server.Handler)
    print("UbeKeso Cart is running on port", port)
    print("Data file:", server.DATA_FILE)
    print("Gmail sending:", "ON" if server.mail_ready() else "OFF (demo mode)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
