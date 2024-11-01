import tkinter as tk
from tkinter import ttk, messagebox
import websockets
import asyncio
import json
import logging
import base64
import numpy as np
from pyfingerprint.pyfingerprint import PyFingerprint
from cryptography.fernet import Fernet
import os
import sqlite3
import threading
from datetime import datetime
from typing import Optional, Dict, Any
import sys


class FingerprintApp:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.server = None
        self.server_thread = None
        self.loop = None
        self.running = True

        # Set up logging
        self.setup_logging()

        # Initialize encryption
        self.setup_encryption()

        # Initialize database
        self.setup_database()

        # Initialize scanner
        self.scanner = self.setup_scanner()

        # Initialize GUI
        self.window = tk.Tk()
        self.window.title("Fingerprint Scanner Service")
        self.window.geometry("400x300")
        self.create_widgets()

        # Start WebSocket server
        self.start_server()

    def setup_logging(self) -> None:
        """Set up logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('fingerprint_service.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )

    def setup_encryption(self) -> None:
        """Initialize encryption key and cipher"""
        try:
            key_path = 'key.key'
            if not os.path.exists(key_path):
                key = Fernet.generate_key()
                with open(key_path, 'wb') as key_file:
                    key_file.write(key)

            with open(key_path, 'rb') as key_file:
                self.key = key_file.read()
            self.cipher = Fernet(self.key)
        except Exception as e:
            logging.error(f"Encryption setup failed: {str(e)}")
            messagebox.showerror("Error", "Failed to setup encryption")
            sys.exit(1)

    def setup_database(self) -> None:
        """Initialize SQLite database"""
        try:
            self.conn = sqlite3.connect('fingerprint.db', check_same_thread=False)
            cursor = self.conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fingerprints (
                    id INTEGER PRIMARY KEY,
                    user_email TEXT UNIQUE NOT NULL,
                    fingerprint_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Add index on user_email for faster lookups
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_user_email 
                ON fingerprints(user_email)
            ''')

            self.conn.commit()
        except Exception as e:
            logging.error(f"Database setup failed: {str(e)}")
            messagebox.showerror("Error", "Failed to setup database")
            sys.exit(1)

    def setup_scanner(self) -> Optional[PyFingerprint]:
        """Initialize fingerprint scanner"""
        try:
            scanner = PyFingerprint('/dev/ttyUSB0', 57600, 0xFFFFFFFF, 0x00000000)
            if scanner.verifyPassword():
                logging.info("Fingerprint scanner initialized successfully")
                return scanner
            else:
                raise Exception("Scanner password verification failed")
        except Exception as e:
            logging.error(f"Scanner initialization failed: {str(e)}")
            return None

    async def handle_websocket(self, websocket: websockets.WebSocketServerProtocol, path: str) -> None:
        """Handle WebSocket connections and messages"""
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    command = data.get('command')

                    response = await {
                        'enroll': self.handle_enrollment,
                        'verify': self.handle_verification
                    }.get(command, lambda *args: {'status': 'error', 'message': 'Invalid command'})(websocket, data)

                    await websocket.send(json.dumps(response))

                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        'status': 'error',
                        'message': 'Invalid JSON data'
                    }))
        except websockets.exceptions.ConnectionClosed:
            logging.info("Client connection closed")
        except Exception as e:
            logging.error(f"WebSocket error: {str(e)}")

    async def handle_enrollment(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> Dict[
        str, str]:
        """Handle fingerprint enrollment process"""
        if not self.scanner:
            return {'status': 'error', 'message': 'Scanner not initialized'}

        try:
            user_email = data.get('email')
            if not user_email:
                return {'status': 'error', 'message': 'Email is required'}

            # Acquire first template
            first_template = await self.acquire_fingerprint(websocket, "Place your finger on the scanner...", 0)

            # Wait for finger removal
            await self.wait_for_finger_removal(websocket)

            # Acquire second template
            second_template = await self.acquire_fingerprint(websocket, "Place the same finger again...", 66)

            # Compare templates
            if np.array_equal(first_template, second_template):
                # Encrypt and store
                encrypted_data = self.cipher.encrypt(first_template.tobytes())
                encoded_data = base64.b64encode(encrypted_data).decode()

                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO fingerprints 
                    (user_email, fingerprint_data, updated_at) 
                    VALUES (?, ?, ?)
                ''', (user_email, encoded_data, datetime.now()))

                self.conn.commit()

                await websocket.send(json.dumps({
                    'status': 'success',
                    'message': 'Fingerprint enrolled successfully',
                    'progress': 100
                }))

                return {'status': 'success', 'message': 'Enrollment complete'}
            else:
                return {'status': 'error', 'message': 'Fingerprints did not match'}

        except Exception as e:
            logging.error(f"Enrollment error: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    async def acquire_fingerprint(self, websocket: websockets.WebSocketServerProtocol,
                                  message: str, progress: int) -> np.ndarray:
        """Acquire fingerprint template from scanner"""
        await websocket.send(json.dumps({
            'status': 'info',
            'message': message,
            'progress': progress
        }))

        while not self.scanner.readImage():
            await asyncio.sleep(0.1)

        self.scanner.convertImage(0x01)
        return self.scanner.downloadCharacteristics()

    async def wait_for_finger_removal(self, websocket: websockets.WebSocketServerProtocol) -> None:
        """Wait for finger to be removed from scanner"""
        await websocket.send(json.dumps({
            'status': 'info',
            'message': 'Remove your finger...',
            'progress': 33
        }))

        while self.scanner.readImage():
            await asyncio.sleep(0.1)

    async def handle_verification(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> Dict[
        str, str]:
        """Handle fingerprint verification process"""
        if not self.scanner:
            return {'status': 'error', 'message': 'Scanner not initialized'}

        try:
            user_email = data.get('email')
            if not user_email:
                return {'status': 'error', 'message': 'Email is required'}

            # Acquire fingerprint
            current_template = await self.acquire_fingerprint(websocket, "Place your finger on the scanner...", 0)

            # Get stored template
            cursor = self.conn.cursor()
            cursor.execute('SELECT fingerprint_data FROM fingerprints WHERE user_email = ?',
                           (user_email,))
            result = cursor.fetchone()

            if result:
                stored_data = base64.b64decode(result[0])
                decrypted_data = self.cipher.decrypt(stored_data)
                stored_template = np.frombuffer(decrypted_data, dtype=np.uint8)

                if np.array_equal(current_template, stored_template):
                    return {'status': 'success', 'message': 'Fingerprint verified'}

            return {'status': 'error', 'message': 'Verification failed'}

        except Exception as e:
            logging.error(f"Verification error: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    def create_widgets(self) -> None:
        """Create and setup GUI widgets"""
        # Status frame
        status_frame = ttk.LabelFrame(self.window, text="Service Status", padding=10)
        status_frame.pack(fill=tk.X, padx=10, pady=5)

        self.status_label = ttk.Label(status_frame, text="Service running")
        self.status_label.pack()

        self.scanner_status = ttk.Label(
            status_frame,
            text="Scanner: " + ("Connected" if self.scanner else "Not Connected"),
            foreground="green" if self.scanner else "red"
        )
        self.scanner_status.pack()

        # Server address
        address_frame = ttk.LabelFrame(self.window, text="Server Information", padding=10)
        address_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(address_frame, text=f"Server running at: ws://{self.host}:{self.port}").pack()

        # Controls
        control_frame = ttk.Frame(self.window, padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(control_frame, text="Stop Server", command=self.stop_server).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Start Server", command=self.start_server).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Exit", command=self.quit_app).pack(side=tk.RIGHT, padx=5)

    def start_server(self) -> None:
        """Start the WebSocket server"""
        if not self.server_thread or not self.server_thread.is_alive():
            self.server_thread = threading.Thread(target=self.run_server)
            self.server_thread.daemon = True
            self.server_thread.start()
            self.status_label.config(text="Service running")
            logging.info("Server started")

    def stop_server(self) -> None:
        """Stop the WebSocket server"""
        if self.server:
            self.running = False
            if self.loop:
                self.loop.call_soon_threadsafe(self.loop.stop)
            self.server = None
            self.status_label.config(text="Service stopped")
            logging.info("Server stopped")

    def run_server(self) -> None:
        """Run the WebSocket server event loop"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        start_server = websockets.serve(self.handle_websocket, self.host, self.port)
        self.server = self.loop.run_until_complete(start_server)

        try:
            self.loop.run_forever()
        finally:
            self.server.close()
            self.loop.run_until_complete(self.server.wait_closed())
            self.loop.close()

    def quit_app(self) -> None:
        """Clean up and quit the application"""
        self.stop_server()
        if self.conn:
            self.conn.close()
        self.window.quit()

    def run(self) -> None:
        """Start the application"""
        self.window.protocol("WM_DELETE_WINDOW", self.quit_app)
        try:
            self.window.mainloop()
        except KeyboardInterrupt:
            self.quit_app()


if __name__ == "__main__":
    try:
        app = FingerprintApp()
        app.run()
    except Exception as e:
        logging.error(f"Application error: {str(e)}")
        sys.exit(1)