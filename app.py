from flask import Flask, request, jsonify, send_from_directory
import asyncio
import json
from datetime import datetime
from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw, VelocityBodyYawspeed
from patterns import (
    fly_square, fly_triangle, fly_circle, fly_star,
    fly_infinity, fly_heart, fly_spiral, fly_figure8
)
import threading
import time

# =========================================
# Flask setup
# =========================================
app = Flask(__name__, static_url_path="", static_folder="static")

# Khởi tạo MAVSDK system
drone = System()

# Flight state tracking
flight_state = {
    "is_flying": False,
    "is_offboard": False,
    "current_pattern": None,
    "mission_count": 0,
    "flight_time": 0,
    "logs": [],
    "velocity_enabled": False
}

# Event loop chạy trong background thread
loop = None
loop_thread = None
pattern_thread = None

def start_background_loop(loop):
    """Chạy event loop trong thread riêng"""
    asyncio.set_event_loop(loop)
    loop.run_forever()

def run_async(coro):
    """Helper để chạy coroutine từ sync context"""
    try:
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=30)
    except Exception as e:
        print(f"Async execution error: {e}")
        return None

# =========================================
# Hàm kết nối PX4
# =========================================
async def connect_drone():
    print("🔗 Connecting to PX4...")
    try:
        await drone.connect(system_address="udpin://0.0.0.0:14540")
        async for state in drone.core.connection_state():
            if state.is_connected:
                print("✅ Connected to PX4")
                return True
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

# =========================================
# Log helper
# =========================================
def add_log(action, status, details=""):
    log_entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "action": action,
        "status": status,
        "details": details
    }
    flight_state["logs"].insert(0, log_entry)
    if len(flight_state["logs"]) > 50:
        flight_state["logs"].pop()
    print(f"[LOG] {action}: {status} - {details}")
    return log_entry

# =========================================
# ROUTES
# =========================================
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

# ---- ARM ----
@app.route("/arm", methods=["POST"])
def arm():
    try:
        run_async(drone.action.arm())
        add_log("ARM", "success", "Drone armed")
        return jsonify({"status": "armed"})
    except Exception as e:
        add_log("ARM", "error", str(e))
        return jsonify({"error": str(e)}), 500

# ---- DISARM ----
@app.route("/disarm", methods=["POST"])
def disarm():
    try:
        # Stop offboard if active
        if flight_state["is_offboard"]:
            run_async(drone.offboard.stop())
            flight_state["is_offboard"] = False
        
        run_async(drone.action.disarm())
        flight_state["is_flying"] = False
        flight_state["velocity_enabled"] = False
        flight_state["current_pattern"] = None
        add_log("DISARM", "success", "Drone disarmed")
        return jsonify({"status": "disarmed"})
    except Exception as e:
        add_log("DISARM", "error", str(e))
        return jsonify({"error": str(e)}), 500

# ---- TAKEOFF ----
@app.route("/takeoff", methods=["POST"])
def takeoff():
    try:
        run_async(drone.action.arm())
        run_async(drone.action.takeoff())
        flight_state["is_flying"] = True
        flight_state["mission_count"] += 1
        add_log("TAKEOFF", "success", "Taking off")
        return jsonify({"status": "taking off"})
    except Exception as e:
        add_log("TAKEOFF", "error", str(e))
        return jsonify({"error": str(e)}), 500

# ---- LAND ----
@app.route("/land", methods=["POST"])
def land():
    try:
        # Stop offboard mode first
        if flight_state["is_offboard"]:
            run_async(drone.offboard.stop())
            flight_state["is_offboard"] = False
        
        run_async(drone.action.land())
        flight_state["is_flying"] = False
        flight_state["current_pattern"] = None
        flight_state["velocity_enabled"] = False
        add_log("LAND", "success", "Landing initiated")
        return jsonify({"status": "landing"})
    except Exception as e:
        add_log("LAND", "error", str(e))
        return jsonify({"error": str(e)}), 500

# ---- RTL (Return to Launch) ----
@app.route("/rtl", methods=["POST"])
def rtl():
    try:
        # Stop offboard mode first
        if flight_state["is_offboard"]:
            run_async(drone.offboard.stop())
            flight_state["is_offboard"] = False
        
        run_async(drone.action.return_to_launch())
        flight_state["current_pattern"] = None
        flight_state["velocity_enabled"] = False
        add_log("RTL", "success", "Returning to launch")
        return jsonify({"status": "returning to launch"})
    except Exception as e:
        add_log("RTL", "error", str(e))
        return jsonify({"error": str(e)}), 500

# ---- EMERGENCY STOP ----
@app.route("/emergency", methods=["POST"])
def emergency():
    try:
        # Try to stop offboard gracefully first
        if flight_state["is_offboard"]:
            run_async(drone.offboard.stop())
            flight_state["is_offboard"] = False
        
        run_async(drone.action.kill())
        flight_state["is_flying"] = False
        flight_state["current_pattern"] = None
        flight_state["velocity_enabled"] = False
        add_log("EMERGENCY", "success", "Emergency stop activated")
        return jsonify({"status": "emergency stop"})
    except Exception as e:
        add_log("EMERGENCY", "error", str(e))
        return jsonify({"error": str(e)}), 500

# ---- PATTERN ----
@app.route("/pattern", methods=["POST"])
def pattern():
    global pattern_thread
    
    try:
        # Nếu đã có pattern chạy, từ chối request mới
        if flight_state["current_pattern"] is not None:
            return jsonify({"error": "Pattern already running"}), 400
        
        data = request.get_json()
        shape = data.get("shape", "square").lower()
        size = float(data.get("size", 5))
        height = -abs(float(data.get("height", 5)))
        delay = float(data.get("speed", 0.5))

        # Map pattern functions
        pattern_map = {
            "square": lambda: fly_square(drone, size, height, delay),
            "triangle": lambda: fly_triangle(drone, size, height, delay),
            "circle": lambda: fly_circle(drone, size, height, 30, delay),
            "star": lambda: fly_star(drone, size, height, delay),
            "infinity": lambda: fly_infinity(drone, size, height, 40, delay),
            "heart": lambda: fly_heart(drone, size, height, 50, delay),
            "spiral": lambda: fly_spiral(drone, size, height, 30, delay),
            "figure8": lambda: fly_figure8(drone, size, height, 40, delay)
        }

        if shape not in pattern_map:
            add_log("PATTERN", "error", f"Unknown shape: {shape}")
            return jsonify({"error": "unknown shape"}), 400

        flight_state["current_pattern"] = shape
        add_log("PATTERN", "started", f"{shape} pattern initiated")

        # Execute pattern asynchronously trong event loop
        def execute_pattern():
            try:
                run_async(pattern_map[shape]())
                add_log("PATTERN", "success", f"{shape} pattern completed")
            except Exception as e:
                add_log("PATTERN", "error", f"{shape} failed: {str(e)}")
            finally:
                flight_state["current_pattern"] = None
                flight_state["is_offboard"] = False

        # Tạo thread mới cho pattern
        pattern_thread = threading.Thread(target=execute_pattern, daemon=True)
        pattern_thread.start()

        return jsonify({"status": f"{shape} pattern started"})
    
    except Exception as e:
        flight_state["current_pattern"] = None
        add_log("PATTERN", "error", str(e))
        return jsonify({"error": str(e)}), 500

# ---- PREPARE OFFBOARD MODE ----
@app.route("/offboard/start", methods=["POST"])
def offboard_start():
    try:
        if flight_state["is_offboard"]:
            return jsonify({"status": "offboard already active"})

        async def start_offboard():
            await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))
            await drone.offboard.start()
        
        run_async(start_offboard())
        flight_state["is_offboard"] = True
        flight_state["velocity_enabled"] = True
        flight_state["is_flying"] = True
        add_log("OFFBOARD", "success", "Offboard mode started")
        return jsonify({"status": "offboard started"})
    except OffboardError as e:
        add_log("OFFBOARD", "error", str(e))
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        add_log("OFFBOARD", "error", str(e))
        return jsonify({"error": str(e)}), 500

# ---- STOP OFFBOARD MODE ----
@app.route("/offboard/stop", methods=["POST"])
def offboard_stop():
    try:
        if not flight_state["is_offboard"]:
            return jsonify({"status": "offboard not active"})

        async def stop_offboard():
            await drone.offboard.stop()
        
        run_async(stop_offboard())
        flight_state["is_offboard"] = False
        flight_state["velocity_enabled"] = False
        add_log("OFFBOARD", "success", "Offboard mode stopped")
        return jsonify({"status": "offboard stopped"})
    except Exception as e:
        add_log("OFFBOARD", "error", str(e))
        return jsonify({"error": str(e)}), 500

# ---- VELOCITY CONTROL (Keyboard) ----
@app.route("/velocity", methods=["POST"])
def velocity():
    try:
        # Only allow velocity commands if offboard is active and enabled
        if not flight_state["is_offboard"] or not flight_state["velocity_enabled"]:
            return jsonify({"error": "offboard mode not active"}), 400

        data = request.get_json()
        vx = float(data.get("vx", 0))
        vy = float(data.get("vy", 0))
        vz = float(data.get("vz", 0))
        yaw_rate = float(data.get("yaw_rate", 0))
        
        async def set_velocity():
            try:
                await drone.offboard.set_velocity_body(
                    VelocityBodyYawspeed(vx, vy, vz, yaw_rate)
                )
            except Exception as e:
                print(f"Velocity command error: {e}")
        
        run_async(set_velocity())
        return jsonify({"status": "velocity set"})
    
    except Exception as e:
        print(f"Velocity endpoint error: {e}")
        return jsonify({"error": str(e)}), 500

# ---- TELEMETRY ----
@app.route("/telemetry", methods=["GET"])
def telemetry():
    async def get_telemetry():
        try:
            # Position
            pos_task = asyncio.create_task(drone.telemetry.position().__anext__())
            
            # Battery
            battery_task = asyncio.create_task(drone.telemetry.battery().__anext__())
            
            # GPS info
            gps_task = asyncio.create_task(drone.telemetry.gps_info().__anext__())
            
            # Flight mode
            mode_task = asyncio.create_task(drone.telemetry.flight_mode().__anext__())
            
            # Armed status
            armed_task = asyncio.create_task(drone.telemetry.armed().__anext__())
            
            # Wait for all with timeout
            pos, battery, gps, mode, armed = await asyncio.wait_for(
                asyncio.gather(
                    pos_task, battery_task, gps_task, mode_task, armed_task,
                    return_exceptions=True
                ),
                timeout=5.0
            )
            
            return {
                "position": {
                    "lat": pos.latitude_deg if not isinstance(pos, Exception) else 0,
                    "lon": pos.longitude_deg if not isinstance(pos, Exception) else 0,
                    "abs_alt": pos.absolute_altitude_m if not isinstance(pos, Exception) else 0,
                    "rel_alt": pos.relative_altitude_m if not isinstance(pos, Exception) else 0
                },
                "battery": {
                    "voltage": battery.voltage_v if not isinstance(battery, Exception) else 0,
                    "remaining": battery.remaining_percent if not isinstance(battery, Exception) else 0
                },
                "gps": {
                    "satellites": gps.num_satellites if not isinstance(gps, Exception) else 0,
                    "fix_type": str(gps.fix_type) if not isinstance(gps, Exception) else "NO_FIX"
                },
                "flight_mode": str(mode) if not isinstance(mode, Exception) else "UNKNOWN",
                "is_armed": armed if not isinstance(armed, Exception) else False,
                "state": flight_state
            }
        except asyncio.TimeoutError:
            print("Telemetry timeout")
            return {
                "position": {"lat": 0, "lon": 0, "abs_alt": 0, "rel_alt": 0},
                "battery": {"voltage": 0, "remaining": 0},
                "gps": {"satellites": 0, "fix_type": "NO_FIX"},
                "flight_mode": "UNKNOWN",
                "is_armed": False,
                "state": flight_state
            }
        except Exception as e:
            print(f"Telemetry error: {e}")
            return {
                "position": {"lat": 0, "lon": 0, "abs_alt": 0, "rel_alt": 0},
                "battery": {"voltage": 0, "remaining": 0},
                "gps": {"satellites": 0, "fix_type": "NO_FIX"},
                "flight_mode": "UNKNOWN",
                "is_armed": False,
                "state": flight_state
            }
    
    result = run_async(get_telemetry())
    return jsonify(result)

# ---- FLIGHT LOGS ----
@app.route("/logs", methods=["GET"])
def get_logs():
    return jsonify({"logs": flight_state["logs"]})

# ---- CLEAR LOGS ----
@app.route("/logs/clear", methods=["POST"])
def clear_logs():
    flight_state["logs"] = []
    add_log("SYSTEM", "success", "Logs cleared")
    return jsonify({"status": "logs cleared"})

# ---- SYSTEM STATUS ----
@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "connected": True,
        "flight_state": flight_state
    })

# =========================================
# MAIN ENTRY
# =========================================
if __name__ == "__main__":
    # Tạo event loop mới trong thread riêng
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=start_background_loop, args=(loop,), daemon=True)
    loop_thread.start()
    
    # Kết nối drone
    time.sleep(1)  # Wait for loop to start
    connected = run_async(connect_drone())
    
    if not connected:
        print("❌ Failed to connect to drone")
    else:
        print("🚀 Server starting on http://0.0.0.0:8081")
    
    app.run(host="0.0.0.0", port=8081, debug=False, threaded=True)