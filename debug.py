from pathlib import Path

import cassini

cassini.status(printer="192.168.0.234", debug=True)

# cassini.upload(
#     Path("/Users/milo/Library/CloudStorage/Dropbox-OMRF/smithy/3d_printing/calibration_models/M68_calibration/boxes_of_calibration/1.5.goo"),
#     "192.168.0.234",
#     False
# )
