from ..globals import initialize

initialize()


def main():
    from .service import RemoteShellService

    service = RemoteShellService()
    service.run()


if __name__ == "__main__":
    main()
