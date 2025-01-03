// script.js - Complete code for managing printer status, displaying and deleting files

let selectedFile = null;

document.addEventListener('DOMContentLoaded', (event) => {
    fetchPrintStatus();
    fetchFiles();
    loadPrinterIP();
});

function loadPrinterIP() {
    fetch('/get-printer-ip')
        .then(response => response.json())
        .then(data => {
            if (data.ip) {
                document.getElementById('printer-ip').value = data.ip;
            } else {
                console.error('Error loading IP:', data.error);
            }
        });
}

document.addEventListener('DOMContentLoaded', (event) => {
    loadPrinterIP();
});

// setInterval(loadPrinterIP, 5000); //Update status every 5 seconds

function saveIP() {
    let ipField = document.getElementById('printer-ip');
    let saveBtn = document.querySelector('.save-ip-btn'); // Selecting the Save button
    let newIP = ipField.value;

    fetch('/set-printer-ip', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ip: newIP
            }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                alert('Printer IP updated!');
                ipField.readOnly = true; // Make the IP field read-only again
                saveBtn.style.display = 'none'; // Hide the Save button
            } else {
                console.error('Error saving IP:', data.error);
            }
        });
}

function editIP() {
    let ipField = document.getElementById('printer-ip');
    let saveBtn = document.querySelector('.save-ip-btn'); // Selecting the Save button

    ipField.readOnly = false;
    ipField.focus();
    ipField.select();

    saveBtn.style.display = 'inline-block'; // Show Save button
}



// script.js - Complete code for managing printer status, displaying, uploading and deleting files

// ... existing functions ...

function uploadFile() {
    let input = document.createElement('input');
    input.type = 'file';
    input.onchange = e => {
        let file = e.target.files[0];
        let formData = new FormData();
        formData.append('file', file);

        showLoadingIndicator('Uploading...');

        let xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload', true);

        xhr.upload.onprogress = function(e) {
            if (e.lengthComputable) {
                let percentComplete = (e.loaded / e.total) * 100;
                updateLoadingPercentage(percentComplete);
            }
        };

        xhr.onloadstart = function(e) {
            updateLoadingPercentage(0); // Initializing the progress bar to 0%
        };

        xhr.onload = function() {
            if (xhr.status === 200) {
                updateLoadingPercentage(100); // Done, set the progress bar to 100%
                hideLoadingIndicator();
                alert('Upload complete!');
                fetchFiles(); // Update list after upload
            } else {
                alert('An error occurred during the upload.');
            }
        };

        xhr.onerror = function() {
            hideLoadingIndicator();
            alert('An error occurred during the upload.');
        };

        xhr.send(formData);
    };
    input.click(); // Open the file selection dialog
}


function printSelectedFile() {
    if (selectedFile) {
        showLoadingIndicator('Preparing print...');
        checkProgress(selectedFile); // Start checking progress

        fetch('/print-file', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    filename: selectedFile
                }),
            })
            .then(response => response.json())
            .then(data => {
                updatePrintProgress(50); // Updated to 50% after printSelectedFile finishes
                alert(data.message); // Show a message to the user
            })
            .catch(error => {
                hideLoadingIndicator();
                console.error('Error:', error);
            });
    }
}

function updatePrintProgress(percent) {
    showLoadingIndicator(`Printing... (${percent}%)`);
    updateLoadingPercentage(percent);


    if (percent >= 100) {
        setTimeout(hideLoadingIndicator, 1000); // Hide the cogwheel after a short delay to allow the user to see that the print is complete
    }
}




// Function to display the charging indicator with message and percentage
function showLoadingIndicator(message) {
    // Create and display a gear wheel and percentage message here
    // You can use a div with a CSS spinner or a gear image
    let loadingDiv = document.getElementById('loading-indicator');
    if (!loadingDiv) {
        loadingDiv = document.createElement('div');
        loadingDiv.id = 'loading-indicator';
        loadingDiv.innerHTML = `
            <div class="loading-spinner"></div>
            <p>${message}</p>
            <p id="loading-percentage">0%</p>`;
        document.body.appendChild(loadingDiv);
    }
}

// Function to hide the loading indicator
function hideLoadingIndicator() {
    let loadingDiv = document.getElementById('loading-indicator');
    if (loadingDiv) {
        loadingDiv.remove();
    }
}




function updateLoadingPercentage(percent) {
    // Update UI with upload progress
    let percentageText = document.getElementById('loading-percentage');
    if (percentageText) {
        percentageText.innerText = `${percent.toFixed(2)}%`;
    }
    // If you have a progress bar, update its width here as well
}


// ... the rest of your script ...

function checkProgress(filename) {
    fetch(`/progress/${filename}`)
        .then(response => response.json())
        .then(data => {
            updatePrintProgress(data.progress);
            if (data.progress < 100) {
                setTimeout(() => checkProgress(filename), 1000); // Ask every second
            }
        })
        .catch(error => console.error('Error:', error));
}


//



function fetchPrintStatus() {
    fetch('/print-status')
        .then(response => response.json())
        .then(data => {
            document.getElementById('status').innerText = data.status;
            let progressBar = document.getElementById('progress-bar');
            let progressText = document.getElementById('progress-text');
            let progressValue = parseFloat(data.progress).toFixed(2);
            progressBar.style.width = progressValue + '%';
            progressText.innerText = progressValue + '%';
            // Update the capsule ONLINE/OFFLINE
            const onlineStatusElement = document.getElementById('online-status');
            if (data.is_online) {
                onlineStatusElement.classList.remove('offline');
                onlineStatusElement.classList.add('online');
                onlineStatusElement.textContent = 'ONLINE';
            } else {
                onlineStatusElement.classList.remove('online');
                onlineStatusElement.classList.add('offline');
                onlineStatusElement.textContent = 'OFFLINE';
            }
        })
        .catch(error => {
            console.error('Error:', error);
            document.getElementById('status').innerText = 'Error loading status.';
        });
}

function fetchFiles() {
    fetch('/files')
        .then(response => response.json())
        .then(filesInfo => {
            let tableRows = filesInfo.map(fileInfo =>
                `<tr onclick="selectFile('${fileInfo.name}')">
                    <td>${fileInfo.name}</td>
                    <td>${fileInfo.size} Mo</td>
                </tr>`
            ).join('');
            document.getElementById('file-list').querySelector('tbody').innerHTML = tableRows;
        })
        .catch(error => {
            console.error('Error:', error);
            document.getElementById('file-list').querySelector('tbody').innerHTML = '<tr><td colspan="2">Error loading files.</td></tr>';
        });
}

function selectFile(filename) {
    selectedFile = filename;
    document.querySelectorAll('.file-list tr').forEach(tr => {
        tr.classList.remove('selected');
    });
    const selectedRow = [...document.querySelectorAll('.file-list tr')].find(tr => tr.cells[0].textContent === filename);
    if (selectedRow) {
        selectedRow.classList.add('selected');
    }
}


function deleteSelectedFile() {
    if (selectedFile) {
        fetch('/delete-file', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    filename: selectedFile
                }),
            })
            .then(response => response.json())
            .then(data => {
                alert(data.message); // Show a message to the user
                fetchFiles(); // Update list after deletion
            })
            .catch(error => console.error('Error:', error));
    }
}

setInterval(fetchPrintStatus, 5000); // Update status every 5 seconds
