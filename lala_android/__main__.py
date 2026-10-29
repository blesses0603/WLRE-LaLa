def main():
    try:
        from .app import run_app
    except ImportError as exc:
        raise SystemExit('Android UI 預覽需要安裝 Kivy；此版本並非可安裝 APK。') from exc
    run_app()


if __name__ == '__main__':
    main()
