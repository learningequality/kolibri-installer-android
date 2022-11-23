from ..globals import initialize

initialize()


def main():
    from .activity import MainActivity

    activity = MainActivity()
    activity.run()


if __name__ == "__main__":
    main()
