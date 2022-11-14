from ..globals import initialize

initialize()


def main():
    from .service import WorkersService

    service = WorkersService()
    service.run()


if __name__ == "__main__":
    main()
