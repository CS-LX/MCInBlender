"""Blender events to SDL3 scancodes used by the current SkyCraft bridge."""
SCANCODES = {chr(ord('A')+i): 4+i for i in range(26)}
SCANCODES.update(dict(zip(['ONE','TWO','THREE','FOUR','FIVE','SIX','SEVEN','EIGHT','NINE','ZERO'], range(30,40))))
SCANCODES.update({f'F{i}': 57+i for i in range(1,13)})
SCANCODES.update({
    'RET':40, 'ESC':41, 'BACK_SPACE':42, 'TAB':43, 'SPACE':44,
    'MINUS':45, 'EQUAL':46, 'LEFT_BRACKET':47, 'RIGHT_BRACKET':48,
    'BACK_SLASH':49, 'SEMI_COLON':51, 'QUOTE':52, 'ACCENT_GRAVE':53,
    'COMMA':54, 'PERIOD':55, 'SLASH':56, 'CAPSLOCK':57,
    'INSERT':73, 'HOME':74, 'PAGE_UP':75, 'DEL':76, 'END':77, 'PAGE_DOWN':78,
    'RIGHT_ARROW':79, 'LEFT_ARROW':80, 'DOWN_ARROW':81, 'UP_ARROW':82,
    'LEFT_CTRL':224, 'LEFT_SHIFT':225, 'LEFT_ALT':226, 'OSKEY':227,
    'RIGHT_CTRL':228, 'RIGHT_SHIFT':229, 'RIGHT_ALT':230,
    'NUMPAD_ENTER':88, 'NUMPAD_0':98, 'NUMPAD_PERIOD':99,
})
SCANCODES.update({f'NUMPAD_{i}':88+i for i in range(1,10)})
BUTTONS = {'LEFTMOUSE':1, 'MIDDLEMOUSE':2, 'RIGHTMOUSE':3, 'BUTTON4MOUSE':4, 'BUTTON5MOUSE':5}
