#!/usr/bin/python3
import argparse
import shutil
from pathlib import Path


def get_locales(locales_dir):
    return (l for l in locales_dir.iterdir() if l.is_dir())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cleanup_dir", type=Path, nargs="*")
    parser.add_argument("-l", "--locales-dir", type=Path, action="append", default=[])
    args = parser.parse_args()

    include_locale_names = set(["en"])

    for locales_dir in args.locales_dir:
        locales = get_locales(locales_dir)
        include_locale_names.update(locale.name for locale in locales)

    print("Included locales: {}".format(include_locale_names))

    for cleanup_dir in args.cleanup_dir:
        locales = get_locales(cleanup_dir)
        remove_locales = (l for l in locales if l.name not in include_locale_names)
        for remove_locale in remove_locales:
            print("Removing locale '{}'".format(remove_locale.absolute()))
            shutil.rmtree(remove_locale.absolute())


if __name__ == "__main__":
    main()
