import time
from pathlib import Path
from typing import Literal

from flask import Flask, Response, jsonify, render_template, request
from loguru import logger
from werkzeug.utils import secure_filename

from cassini.cli import do_print, do_upload
from cassini.exceptions import PrintersError
from cassini.saturn_printer import PrintInfoStatus, SaturnPrinter

app = Flask(__name__)

printer_ip = Literal["192.168.0.235"]
UPLOAD_FOLDER = Path("uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
UNABLE_TO_READ_ADDRESS = Literal["The printer's IP address could not be read."]

if not UPLOAD_FOLDER.exists():
    UPLOAD_FOLDER.mkdir()


# TODO: figure out gettext or some other localization library
@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/get-printer-ip", methods=["GET"])
def get_printer_ip() -> Response:
    try:
        printers = SaturnPrinter().find_printers()
        match len(printers):
            case 0:
                msg = "No printers were found"
                raise PrintersError(msg)
            case 1:
                sp = printers[0]
                ip = sp.addr[0]
                logger.info(f"Address IP: {ip}")  # Pour le débogage
                return jsonify({"ip": ip})  # Renvoie une réponse JSON
            case _:
                msg = "Multiple printers found"
                raise PrintersError(msg)
    except Exception as e:
        msg = "No printer was found on the network"
        logger.error(f"{msg}: {e}")  # Pour le débogage
        return jsonify({"error": str(e)})  # Renvoie une erreur en JSON


def read_printer_ip() -> str | None:
    try:
        sp = SaturnPrinter().find_printers()[0]
        return sp.addr[0]
    except Exception as e:
        # print(f"Erreur lors de la lecture de l'adresse IP : {e}")
        msg = f"Error reading IP address: {e}"
        logger.error(msg)
        return None


@app.route("/set-printer-ip", methods=["POST"])
def set_printer_ip():
    try:
        new_ip = request.json.get("ip")
        # print(f"Tentative de mise à jour de l'adresse IP de l'imprimante : {new_ip}")
        logger.info(f"Attempting to update the printer's IP address: {new_ip}")
        with open("printer_ip.txt", "w") as file:
            file.write(new_ip)
        print("The printer's IP address has been updated.")
        return jsonify({"message": "IP updated"})
    except Exception as e:
        print(f"Error updating IP address : {e}")
        return jsonify({"error": str(e)})


@app.route("/print-status")
def print_status():
    printer_ip = read_printer_ip()
    if printer_ip is None:
        return jsonify({"error": UNABLE_TO_READ_ADDRESS})
    try:
        sp = SaturnPrinter().find_printer(printer_ip)
        output = PrintInfoStatus(sp.desc["Data"]["Status"]["PrintInfo"]["Status"]).name

        is_online = bool(sp.desc["Data"]["Status"]["CurrentStatus"])

        current_layer = sp.desc["Data"]["Status"]["PrintInfo"]["CurrentLayer"]
        total_layers = sp.desc["Data"]["Status"]["PrintInfo"]["TotalLayer"]
        progress = (int(current_layer) / int(total_layers)) * 100

        return jsonify(
            {
                "status": output,
                "current_layer": current_layer,
                "total_layers": total_layers,
                "progress": progress,
                "is_online": is_online,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/upload", methods=["POST"])
def upload_file():
    if file := request.files["file"]:
        filename = secure_filename(file.filename)
        filepath = app.config["UPLOAD_FOLDER"].joinpath(filename)
        file.save(filepath)
        return jsonify({"message": "File uploaded successfully", "filename": filename})
    return jsonify({"error": "No file"})


@app.route("/files")
def list_files():
    files = app.config["UPLOAD_FOLDER"].iterdir()
    files_info = []
    for file in files:
        filepath = app.config["UPLOAD_FOLDER"].joinpath(file)
        size = filepath.stat().st_size / (1024 * 1024)  # Convertir en mégaoctets
        files_info.append({"name": file, "size": round(size, 2)})  # Arrondir à deux décimales
    return jsonify(files_info)


progress_status = {}


def print_file_after_upload(filename):
    printer_ip = read_printer_ip()
    if printer_ip is None:
        return jsonify({"error": UNABLE_TO_READ_ADDRESS})
    # Envoie la mise à jour de progression à 75%
    progress_status[filename] = 75  # Mettre à jour l'état d'avancement
    time.sleep(10)
    do_print(printer=printer_ip, filename=filename)

    # Envoie la mise à jour de progression à 100%
    progress_status[filename] = 100  # Mettre à jour l'état d'avancement après impression


@app.route("/progress/<filename>")
def get_progress(filename):
    return jsonify({"progress": progress_status.get(filename, 0)})


@app.route("/print-file", methods=["POST"])
def print_file():
    printer_ip = read_printer_ip()
    if printer_ip is None:
        return jsonify({"error": UNABLE_TO_READ_ADDRESS})

    filename = request.json["filename"]
    filepath = app.config["UPLOAD_FOLDER"].joinpath(filename)

    do_upload(printer=printer_ip, filename=filepath)

    # Ici, nous supposons que la mise à jour de la progression est gérée dans un autre mécanisme
    return jsonify({"message": f"Uploading {filename}, printing will start shortly."})


@app.route("/delete-file", methods=["POST"])
def delete_file():
    filename = request.json["filename"]
    filepath = app.config["UPLOAD_FOLDER"].joinpath(filename)

    try:
        filepath.unlink()
        return jsonify({"message": f"File {filename} deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)})


def run_rpp(host: str = "127.0.0.1", port: int = 5001, debug: bool = False):
    if debug:
        app.run(debug=True, port=port, host=host)  # noqa: S201
    else:
        from waitress import serve

        listen_on = f"{host}:{port}"
        serve(app, listen=listen_on)


if __name__ == "__main__":
    app.run(debug=True, port=5001, host="127.0.0.1")  # noqa: S201
