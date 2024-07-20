import re
import subprocess
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from loguru import logger
from werkzeug.utils import secure_filename

from cassini import status
from cassini.saturn_printer import SaturnPrinter

app = Flask(__name__)

printer_ip = "192.168.1.50"
UPLOAD_FOLDER = Path("uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not UPLOAD_FOLDER.exists():
    UPLOAD_FOLDER.mkdir()


# TODO: figure out gettext or some other localization library
@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/get-printer-ip", methods=["GET"])
def get_printer_ip() -> Response:
    try:
        sp = SaturnPrinter().find_printers()[0]
        ip = sp.addr[0]
        logger.info(f"Address IP: {ip}")  # Pour le débogage
        return jsonify({"ip": ip})  # Renvoie une réponse JSON
    except Exception as e:
        msg = "No printer was found on the network"
        logger.errorprint(f"{msg}: {e}")  # Pour le débogage
        return jsonify({"error": str(e)})  # Renvoie une erreur en JSON


def read_printer_ip() -> str:
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
        print("L'adresse IP de l'imprimante a été mise à jour.")
        return jsonify({"message": "IP updated"})
    except Exception as e:
        print(f"Erreur lors de la mise à jour de l'adresse IP : {e}")
        return jsonify({"error": str(e)})


@app.route("/print-status")
def print_status():
    printer_ip = read_printer_ip()
    if printer_ip is None:
        return jsonify({"error": "L'adresse IP de l'imprimante n'a pas pu être lue."})

    try:
        # cmd = ["./cassini.py", "-p", printer_ip, "status"]
        # result = subprocess.run(cmd, capture_output=True, text=True)
        # output = result.stdout.strip()
        sp = SaturnPrinter(printer_ip)
        output = status(printer_addr=printer_ip)

        is_online = printer_ip in output

        if match := re.search(r"Layers: (\d+)/(\d+)", output):
            current_layer, total_layers = match.groups()
            progress = (int(current_layer) / int(total_layers)) * 100
        else:
            current_layer, total_layers, progress = "N/A", "N/A", 0

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


def run_command(cmd, on_complete=None, *args):
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    for line in iter(process.stdout.readline, ""):
        print(line, end="")
        if "100%" in line:
            break

    process.terminate()

    if on_complete:
        on_complete(*args)


progress_status = {}


def print_file_after_upload(filename):
    printer_ip = read_printer_ip()
    if printer_ip is None:
        return jsonify({"error": "L'adresse IP de l'imprimante n'a pas pu être lue."})
    # Envoie la mise à jour de progression à 75%
    progress_status[filename] = 75  # Mettre à jour l'état d'avancement
    time.sleep(10)
    print_cmd = ["./cassini.py", "--printer", printer_ip, "print", filename]
    subprocess.run(print_cmd, capture_output=True, text=True, check=False)
    # Envoie la mise à jour de progression à 100%
    progress_status[filename] = 100  # Mettre à jour l'état d'avancement après impression


@app.route("/progress/<filename>")
def get_progress(filename):
    return jsonify({"progress": progress_status.get(filename, 0)})


@app.route("/print-file", methods=["POST"])
def print_file():
    printer_ip = read_printer_ip()
    if printer_ip is None:
        return jsonify({"error": "L'adresse IP de l'imprimante n'a pas pu être lue."})

    filename = request.json["filename"]
    filepath = app.config["UPLOAD_FOLDER"].joinpath(filename)

    upload_cmd = ["./cassini.py", "--printer", printer_ip, "upload", filepath]
    upload_thread = threading.Thread(target=run_command, args=(upload_cmd, print_file_after_upload, filename))
    upload_thread.start()

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


if __name__ == "__main__":
    app.run(debug=True, port=5001, host="0.0.0.0")
