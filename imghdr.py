# --- Заглушка для imghdr ---
# Позволяет библиотекам, которые пытаются импортировать imghdr, не падать с ошибкой.
def what(file, h=None):
    try:
        if hasattr(file, "read"):
            file.read(32)
            try:
                file.seek(0)
            except:
                pass
        else:
            with open(file, "rb") as f:
                f.read(32)
    except:
        pass
    return None
