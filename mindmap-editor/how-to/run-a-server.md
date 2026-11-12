---
title: Share maps between your devices with a server
---

# Share maps between your devices with a server

The Mind Map Editor normally keeps your map in one browser. If you run the small mind map server on a computer on your home network, such as a Raspberry Pi, every phone, tablet and computer on that network can open and save the same maps.

The server is [`mindmap_server.py`](../../mindmap_server.py). It needs only Python 3, with nothing to install. It serves the editor and keeps your maps as `.zip` files in one folder.

**There is no password.** Anyone who can reach the server can read and change the maps, so run it only on a network you trust. To use it away from home, put the server and your devices on a private network such as [Tailscale](https://tailscale.com/) rather than opening it to the internet.

## Get the files

Clone the repository onto the computer that will run the server:

```
git clone https://github.com/romilly/browser-based-tools.git
cd browser-based-tools
```

The server needs `mindmap_server.py` and `mindmap-editor.html` side by side, as they are in the repository. It uses only Python's standard library, so there is nothing to install: you don't need a virtual environment or `pip`. (The packages in `requirements-dev.txt` are only for running the tests.)

## Run the server

In the repository folder, run [`start-mmserver.py`](../../start-mmserver.py):

```
python3 start-mmserver.py
```

It prints `Serving on port 8765; Ctrl+C to stop` and keeps running until you press Ctrl+C.

Then, on any device on the network, browse to `http://<server name or address>:8765/`, for example `http://raspberrypi.local:8765/`. The **File** menu now has **Open from server…** and **Save to server**.

### Changing the folder or port

The maps are kept in `~/mindmaps`, which is created if it doesn't exist. To change that, edit the `start_mind_map_server(...)` line in `start-mmserver.py`. It takes:

- the folder for the maps;
- `port=8765`, the port to listen on;
- `host='0.0.0.0'`, which accepts connections from the whole network. Use `'127.0.0.1'` for this computer only;
- `editor=`, the path of `mindmap-editor.html`, if it isn't beside `mindmap_server.py`.

For example: `start_mind_map_server('~/maps', port=8080)`.

## Run it as a service (optional)

If you want the server always running, on Linux systemd can start the server when the computer boots and restart it if it fails. These steps use the user `pi` and a clone at `/home/pi/browser-based-tools`; change both to suit.

1. Stop any copy you started by hand, because only one program can use the port.

2. Create the file `/etc/systemd/system/mindmap-server.service`, for example with `sudo nano /etc/systemd/system/mindmap-server.service`, containing:

   ```ini
   [Unit]
   Description=Mind map server
   After=network-online.target
   Wants=network-online.target

   [Service]
   User=pi
   WorkingDirectory=/home/pi/browser-based-tools
   ExecStart=/usr/bin/python3 start-mmserver.py
   Environment=PYTHONUNBUFFERED=1
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

   `PYTHONUNBUFFERED=1` makes the server's messages appear in the log straight away.

3. Start the service, and have it start at every boot:

   ```
   sudo systemctl daemon-reload
   sudo systemctl enable --now mindmap-server
   ```

4. Check that it is running:

   ```
   systemctl status mindmap-server
   ```

   It should say `active (running)`. To follow its messages, run `journalctl -u mindmap-server -f`.

To stop the service, run `sudo systemctl stop mindmap-server`. To stop it starting at boot, run `sudo systemctl disable mindmap-server`.

### Updating

Run `git pull` in the clone.

- A new version of the editor is used straight away: reload the page on each device.
- A new version of the server needs a restart: `sudo systemctl restart mindmap-server`.

The service runs whatever is checked out in the clone, so keep that clone on the `main` branch.

## If you can't reach it

On the server, check that it is listening and answering:

```
ss -ltn | grep 8765
curl http://localhost:8765/api/maps
```

`curl` should print a list of maps, or `[]` if there are none yet.

- **Nothing is listening:** the server isn't running. Check `systemctl status mindmap-server` and the log.
- **It works on the server but not from another device:**
  - Check the firewall. If `sudo ufw status` says it is active, run `sudo ufw allow 8765/tcp`.
  - Try the server's address instead of its name. `hostname -I` shows it. If the address works but the name doesn't, the problem is with names on your network, not with the server.
- **The File menu has no server commands:** the page didn't come from the server. Open it from the server's address, not from GitHub Pages or a saved copy.

## Link to a map

Each map on the server has its own address: the server's address followed by `?map=` and the map's name, for example `http://raspberrypi.local:8765/?map=holiday_in_the_netherlands`. The address bar shows it whenever the open map came from the server, so copy it from there.

Put the address in a note to open the map with one click. In Obsidian, for example:

```markdown
[Holiday mind map](http://raspberrypi.local:8765/?map=holiday_in_the_netherlands)
```

While a map from the server is open:

- **Save to server** and **Ctrl+S** save it back under the same name, even if you rename its central topic, so the link keeps working. **Save** still downloads a copy.
- If you try to close the tab or leave the page with changes not saved to the server, the browser asks first.

A link to a map that isn't on the server says so, and leaves the current map as it was.

## Two devices, one map

Each save names the version it replaces. If someone saved the map on another device after you opened it, **Save to server** asks before replacing their version. It also asks before a new map replaces one of the same name already on the server.

## Backing up

The maps are ordinary `.zip` files in the server's folder (`~/mindmaps` unless you changed it), so back up that folder. Each file opens in the editor with **Open**, as well as from the server.

[Mind Map Editor](../index.md)
