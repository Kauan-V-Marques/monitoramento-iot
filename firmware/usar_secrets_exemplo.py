# Se include/secrets.h não existir (ex.: no CI), compila com o arquivo de exemplo.
import os
import shutil

Import("env")  # noqa: F821 (injetado pelo PlatformIO)

destino = os.path.join(env["PROJECT_INCLUDE_DIR"], "secrets.h")  # noqa: F821
if not os.path.exists(destino):
    shutil.copy(os.path.join(env["PROJECT_INCLUDE_DIR"], "secrets.example.h"), destino)  # noqa: F821
    print("secrets.h não encontrado: usando secrets.example.h")
