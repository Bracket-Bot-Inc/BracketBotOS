from bbos import Reader

with Reader('/camera.jpeg') as r:
    while True:
        if r.ready():
            print(r.data['bytesused'])