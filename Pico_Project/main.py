
from machine import Pin
import time

# 三个按钮，各自连接 GPIO 和 GND
buttons = {
    "BUTTON_A": Pin(16, Pin.IN, Pin.PULL_UP),
    "BUTTON_B": Pin(17, Pin.IN, Pin.PULL_UP),
    "BUTTON_C": Pin(18, Pin.IN, Pin.PULL_UP)
}

# 记录之前的按钮状态
last_states = {
    name: button.value()
    for name, button in buttons.items()
}

last_press = {
    name: 0
    for name in buttons
}

while True:
    for name, button in buttons.items():
        current = button.value()

        # 只在按下瞬间发送信号
        if current == 0 and last_states[name] == 1:
            now = time.ticks_ms()

            if time.ticks_diff(now, last_press[name]) > 250:
                print(name)
                last_press[name] = now

        last_states[name] = current

    time.sleep_ms(20)

