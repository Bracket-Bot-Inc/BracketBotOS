from bbos import Reader, Loop

with Reader('/camera.jpeg') as r:
    i = 0
    while Loop.sleep():
        if r.ready():
            i += 1