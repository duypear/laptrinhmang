import asyncio
import math
from mavsdk.offboard import OffboardError, PositionNedYaw

# =========================================
# Helper Functions
# =========================================
async def prepare_offboard(drone, height=-5):
    """Chuẩn bị chế độ offboard"""
    try:
        # Khởi động offboard với vị trí hiện tại
        await drone.offboard.set_position_ned(PositionNedYaw(0, 0, height, 0))
        await asyncio.sleep(0.1)
        await drone.offboard.start()
        print(" Offboard mode started")
        await asyncio.sleep(2)  # Đợi drone ổn định
        
        # Căn chỉnh về điểm gốc (0, 0, height)
        for _ in range(3):
            await drone.offboard.set_position_ned(PositionNedYaw(0, 0, height, 0))
            await asyncio.sleep(0.2)
        
        print(" Drone positioned at origin")
        await asyncio.sleep(1)
    except OffboardError as e:
        print(f" Failed to start Offboard: {e}")
        raise

async def stop_offboard(drone):
    """Dừng chế độ offboard an toàn"""
    try:
        await drone.offboard.stop()
        print(" Offboard mode stopped")
    except Exception as e:
        print(f" Error stopping offboard: {e}")

async def set_position(drone, x, y, z, yaw, delay=0.1):
    """Thiết lập vị trí với kiểm soát lỗi"""
    try:
        await drone.offboard.set_position_ned(PositionNedYaw(x, y, z, yaw))
        await asyncio.sleep(delay)
    except Exception as e:
        print(f"Position error: {e}")
        raise

async def fly_to_position(drone, x, y, z, yaw, duration=3.0):
    """Bay đến vị trí và chờ đủ thời gian"""
    print(f"  → Flying to ({x:.1f}, {y:.1f}, {z:.1f}) yaw={yaw:.0f}°")
    
    # Gửi lệnh liên tục trong khoảng thời gian duration
    steps = int(duration * 10)  # 10Hz update rate
    for _ in range(steps):
        await drone.offboard.set_position_ned(PositionNedYaw(x, y, z, yaw))
        await asyncio.sleep(0.1)
    
    # Giữ vị trí ổn định thêm 2 giây
    for _ in range(20):
        await drone.offboard.set_position_ned(PositionNedYaw(x, y, z, yaw))
        await asyncio.sleep(0.1)

# =========================================
# Basic Patterns
# =========================================
async def fly_square(drone, size=5, height=-5, delay=1.0):
    """Bay hình vuông
    
    Quỹ đạo:
    (0,size) -------- (size,size)
       |                  |
       |                  |
    (0,0)   -------- (size,0)
    
    Bay theo thứ tự: (0,0) → (size,0) → (size,size) → (0,size) → (0,0)
    """
    try:
        await prepare_offboard(drone, height)
        print(f" Starting SQUARE pattern (size={size}m, height={-height}m)")
        
        # Thời gian bay giữa các điểm (phụ thuộc vào delay)
        flight_time = max(3.0, delay * 3)
        
        # 4 góc của hình vuông với góc yaw hướng về điểm tiếp theo
        points = [
            (0,    0,    0),     # Điểm xuất phát
            (size, 0,    90),    # Góc phải dưới - quay sang Đông
            (size, size, 180),   # Góc phải trên - quay sang Bắc  
            (0,    size, 270),   # Góc trái trên - quay sang Tây
            (0,    0,    0),     # Quay về điểm gốc - quay sang Nam
        ]
        
        for i, (x, y, yaw) in enumerate(points):
            print(f"  Point {i+1}/5: ({x}, {y})")
            await fly_to_position(drone, x, y, height, yaw, flight_time)
        
        print(" Square complete")
        await stop_offboard(drone)
        
    except Exception as e:
        print(f" Square error: {e}")
        try:
            await stop_offboard(drone)
        except:
            pass
        raise

async def fly_triangle(drone, size=5, height=-5, delay=1.0):
    """Bay hình tam giác đều"""
    try:
        await prepare_offboard(drone, height)
        print(f" Starting TRIANGLE pattern (size={size}m)")
        
        flight_time = max(3.0, delay * 3)
        
        # 3 đỉnh tam giác đều
        h = size * math.sqrt(3) / 2
        points = [
            (0,      0,  60),    # Đỉnh dưới trái
            (size,   0,  180),   # Đỉnh dưới phải
            (size/2, h,  300),   # Đỉnh trên
            (0,      0,  0),     # Quay về
        ]
        
        for i, (x, y, yaw) in enumerate(points):
            print(f"  Point {i+1}/4: ({x:.1f}, {y:.1f})")
            await fly_to_position(drone, x, y, height, yaw, flight_time)
        
        print(" Triangle complete")
        await stop_offboard(drone)
        
    except Exception as e:
        print(f" Triangle error: {e}")
        try:
            await stop_offboard(drone)
        except:
            pass
        raise

async def fly_circle(drone, radius=5, height=-5, steps=60, delay=0.3):
    """Bay hình tròn với độ mượt cao"""
    try:
        await prepare_offboard(drone, height)
        print(f" Starting CIRCLE pattern (radius={radius}m)")
        
        # Tăng số bước để vòng tròn mượt hơn
        total_steps = max(steps, 100)  # Tối thiểu 100 bước
        
        # Bay đến điểm bắt đầu (bên phải cùng của vòng tròn)
        print(f"  → Moving to start position ({radius}, 0)")
        await fly_to_position(drone, radius, 0, height, 90, 3.0)
        
        # Vẽ vòng tròn với độ mượt cao
        print(f"  → Drawing circle with {total_steps} steps")
        for i in range(total_steps + 1):
            angle = 2 * math.pi * i / total_steps
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            
            # Yaw luôn tiếp tuyến với vòng tròn (hướng theo chiều bay)
            yaw = math.degrees(angle + math.pi/2)
            
            # Gửi lệnh nhiều lần cho mỗi điểm
            repeat = max(3, int(delay * 10))
            for _ in range(repeat):
                await drone.offboard.set_position_ned(PositionNedYaw(x, y, height, yaw))
                await asyncio.sleep(0.1)
        
        # Dừng lại ở điểm kết thúc và giữ vị trí
        final_x = radius * math.cos(2 * math.pi)
        final_y = radius * math.sin(2 * math.pi)
        print(f"  → Holding final position ({final_x:.1f}, {final_y:.1f})")
        for _ in range(20):
            await drone.offboard.set_position_ned(PositionNedYaw(final_x, final_y, height, 90))
            await asyncio.sleep(0.1)
        
        print(" Circle complete")
        await stop_offboard(drone)
        
    except Exception as e:
        print(f" Circle error: {e}")
        try:
            await stop_offboard(drone)
        except:
            pass
        raise

async def fly_star(drone, size=5, height=-5, delay=0.8):
    """Bay hình ngôi sao 5 cánh"""
    try:
        await prepare_offboard(drone, height)
        print(f" Starting STAR pattern (size={size}m)")
        
        flight_time = max(2.5, delay * 2.5)
        
        # 5 đỉnh ngôi sao
        points = []
        for i in range(5):
            angle = 2 * math.pi * i / 5 - math.pi/2
            x = size * math.cos(angle)
            y = size * math.sin(angle)
            points.append((x, y))
        
        # Nối các đỉnh: 0→2→4→1→3→0
        order = [0, 2, 4, 1, 3, 0]
        
        # Vẽ ngôi sao
        for i, idx in enumerate(order):
            x, y = points[idx]
            yaw = math.degrees(math.atan2(y, x))
            print(f"  Point {i+1}/{len(order)}: ({x:.1f}, {y:.1f})")
            await fly_to_position(drone, x, y, height, yaw, flight_time)
        
        print(" Star complete")
        await stop_offboard(drone)
        
    except Exception as e:
        print(f" Star error: {e}")
        try:
            await stop_offboard(drone)
        except:
            pass
        raise

# =========================================
# Advanced Patterns
# =========================================
async def fly_infinity(drone, size=5, height=-5, steps=60, delay=0.3):
    """Bay hình số 8 ngang (∞) với độ mượt cao"""
    try:
        await prepare_offboard(drone, height)
        print(f"∞ Starting INFINITY pattern (size={size}m)")
        
        # Tăng số bước để đường cong mượt hơn
        total_steps = max(steps, 120)
        
        # Bay đến điểm bắt đầu
        start_x = size
        start_y = 0
        print(f"  → Moving to start position ({start_x}, {start_y})")
        await fly_to_position(drone, start_x, start_y, height, 0, 3.0)
        
        # Vẽ hình infinity với độ mượt cao
        print(f"  → Drawing infinity with {total_steps} steps")
        for i in range(total_steps + 1):
            t = 2 * math.pi * i / total_steps
            
            # Lemniscate of Gerono formula
            x = size * math.cos(t)
            y = size * math.sin(t) * math.cos(t)
            
            # Tính yaw theo hướng tiếp tuyến
            if i < total_steps:
                t_next = 2 * math.pi * (i + 1) / total_steps
                x_next = size * math.cos(t_next)
                y_next = size * math.sin(t_next) * math.cos(t_next)
                dx = x_next - x
                dy = y_next - y
                if abs(dx) > 0.01 or abs(dy) > 0.01:
                    yaw = math.degrees(math.atan2(dy, dx))
                else:
                    yaw = 0
            else:
                yaw = 0
            
            # Gửi lệnh nhiều lần cho mỗi điểm
            repeat = max(3, int(delay * 10))
            for _ in range(repeat):
                await drone.offboard.set_position_ned(PositionNedYaw(x, y, height, yaw))
                await asyncio.sleep(0.1)
        
        # Giữ vị trí cuối
        print(f"  → Holding final position")
        for _ in range(20):
            await drone.offboard.set_position_ned(PositionNedYaw(size, 0, height, 0))
            await asyncio.sleep(0.1)
        
        print(" Infinity complete")
        await stop_offboard(drone)
        
    except Exception as e:
        print(f" Infinity error: {e}")
        try:
            await stop_offboard(drone)
        except:
            pass
        raise

async def fly_heart(drone, size=5, height=-5, steps=80, delay=0.3):
    """Bay hình trái tim với độ mượt cao"""
    try:
        await prepare_offboard(drone, height)
        print(f" Starting HEART pattern (size={size}m)")
        
        # Tăng số bước cho đường cong mượt
        total_steps = max(steps, 150)
        
        # Tính điểm bắt đầu (đáy trái tim)
        t_start = 0
        start_x = size * 16 * (math.sin(t_start) ** 3) / 16
        start_y = size * (13 * math.cos(t_start) - 5 * math.cos(2*t_start) - 2 * math.cos(3*t_start) - math.cos(4*t_start)) / 16
        
        print(f"  → Moving to start position ({start_x:.1f}, {start_y:.1f})")
        await fly_to_position(drone, start_x, start_y, height, 90, 3.0)
        
        # Vẽ hình trái tim
        print(f"  → Drawing heart with {total_steps} steps")
        for i in range(total_steps + 1):
            t = 2 * math.pi * i / total_steps
            
            # Heart curve formula
            x = size * 16 * (math.sin(t) ** 3) / 16
            y = size * (13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t)) / 16
            
            # Tính yaw theo hướng tiếp tuyến
            if i < total_steps:
                t_next = 2 * math.pi * (i + 1) / total_steps
                x_next = size * 16 * (math.sin(t_next) ** 3) / 16
                y_next = size * (13 * math.cos(t_next) - 5 * math.cos(2*t_next) - 2 * math.cos(3*t_next) - math.cos(4*t_next)) / 16
                dx = x_next - x
                dy = y_next - y
                if abs(dx) > 0.01 or abs(dy) > 0.01:
                    yaw = math.degrees(math.atan2(dy, dx))
                else:
                    yaw = 90
            else:
                yaw = 90
            
            # Gửi lệnh nhiều lần cho mỗi điểm
            repeat = max(3, int(delay * 10))
            for _ in range(repeat):
                await drone.offboard.set_position_ned(PositionNedYaw(x, y, height, yaw))
                await asyncio.sleep(0.1)
        
        # Giữ vị trí cuối
        print(f"  → Holding final position")
        for _ in range(20):
            await drone.offboard.set_position_ned(PositionNedYaw(start_x, start_y, height, 90))
            await asyncio.sleep(0.1)
        
        print("Heart complete")
        await stop_offboard(drone)
        
    except Exception as e:
        print(f"Heart error: {e}")
        try:
            await stop_offboard(drone)
        except:
            pass
        raise

async def fly_spiral(drone, max_radius=5, height=-5, steps=30, delay=0.4):
    """Bay hình xoắn ốc 5 vòng ra ngoài (không xoắn vào)"""
    try:
        await prepare_offboard(drone, height)
        print(f" Starting SPIRAL pattern (radius={max_radius}m, 5 turns)")
        
        # Tăng số bước cho đường xoắn mượt hơn
        total_steps = max(steps, 100)
        
        # Bay đến trung tâm trước
        print(f"  → Moving to center (0, 0)")
        await fly_to_position(drone, 0, 0, height, 0, 3.0)
        
        # Vòng xoắn ra ngoài với 5 vòng
        print(f"  → Spiraling outward 5 turns with {total_steps} steps...")
        for i in range(total_steps + 1):
            # 5 vòng xoắn (thay vì 3)
            t = 5 * 2 * math.pi * i / total_steps
            radius = max_radius * i / total_steps
            
            x = radius * math.cos(t)
            y = radius * math.sin(t)
            
            # Yaw hướng theo chiều xoắn
            yaw = math.degrees(t + math.pi/2)
            
            # Gửi lệnh nhiều lần cho mỗi điểm
            repeat = max(3, int(delay * 10))
            for _ in range(repeat):
                await drone.offboard.set_position_ned(PositionNedYaw(x, y, height, yaw))
                await asyncio.sleep(0.1)
        
        # Giữ vị trí ngoài cùng
        outer_x = max_radius * math.cos(5 * 2 * math.pi)
        outer_y = max_radius * math.sin(5 * 2 * math.pi)
        print(f"  → Holding outer position ({outer_x:.1f}, {outer_y:.1f})")
        for _ in range(20):
            await drone.offboard.set_position_ned(PositionNedYaw(outer_x, outer_y, height, 90))
            await asyncio.sleep(0.1)
        
        print(" Spiral complete (5 turns outward)")
        await stop_offboard(drone)
        
    except Exception as e:
        print(f" Spiral error: {e}")
        try:
            await stop_offboard(drone)
        except:
            pass
        raise

async def fly_figure8(drone, size=5, height=-5, steps=60, delay=0.3):
    """Bay hình số 8 đứng với độ mượt cao"""
    try:
        await prepare_offboard(drone, height)
        print(f" Starting FIGURE-8 pattern (size={size}m)")
        
        # Tăng số bước cho đường cong mượt
        total_steps = max(steps, 120)
        scale = size / 1.5
        
        # Tính điểm bắt đầu
        t_start = 0
        start_x = scale * math.sin(t_start)
        start_y = scale * math.sin(t_start) * math.cos(t_start)
        
        print(f"  → Moving to start position ({start_x:.1f}, {start_y:.1f})")
        await fly_to_position(drone, start_x, start_y, height, 90, 3.0)
        
        # Vẽ hình số 8
        print(f"  → Drawing figure-8 with {total_steps} steps")
        for i in range(total_steps + 1):
            t = 2 * math.pi * i / total_steps
            
            # Lissajous curve (1:2 ratio for figure-8)
            x = scale * math.sin(t)
            y = scale * math.sin(t) * math.cos(t)
            
            # Tính yaw theo hướng tiếp tuyến
            if i < total_steps:
                t_next = 2 * math.pi * (i + 1) / total_steps
                x_next = scale * math.sin(t_next)
                y_next = scale * math.sin(t_next) * math.cos(t_next)
                dx = x_next - x
                dy = y_next - y
                if abs(dx) > 0.01 or abs(dy) > 0.01:
                    yaw = math.degrees(math.atan2(dy, dx))
                else:
                    yaw = 90
            else:
                yaw = 90
            
            # Gửi lệnh nhiều lần cho mỗi điểm
            repeat = max(3, int(delay * 10))
            for _ in range(repeat):
                await drone.offboard.set_position_ned(PositionNedYaw(x, y, height, yaw))
                await asyncio.sleep(0.1)
        
        # Giữ vị trí cuối
        print(f"  → Holding final position")
        for _ in range(20):
            await drone.offboard.set_position_ned(PositionNedYaw(start_x, start_y, height, 90))
            await asyncio.sleep(0.1)
        
        print(" Figure-8 complete")
        await stop_offboard(drone)
        
    except Exception as e:
        print(f" Figure-8 error: {e}")
        try:
            await stop_offboard(drone)
        except:
            pass
        raise