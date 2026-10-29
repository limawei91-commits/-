# Gargantua black hole render

`gargantua.py` traces every pixel's light ray through Schwarzschild spacetime (numpy, RK4),
so the arch over the shadow, the lower arc and the photon ring come out of the physics.
Like the film, Doppler beaming is off by default (`--doppler` turns it on).

```bash
pip install numpy pillow          # ffmpeg is also needed for video
python3 gargantua.py --width 1920 --height 1080 --out gargantua_1080p.png
python3 gargantua.py --width 1920 --height 1080 --frames 300 --out gargantua_1080p.mp4
```

Useful flags: `--incl` camera elevation (deg), `--dist` camera distance, `--fov`, `--roll`, `--r-out` disk size.
