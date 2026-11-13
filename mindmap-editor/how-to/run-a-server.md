---
title: Share maps between your devices with a server
---

# Share maps between your devices with a server

The Mind Map Editor normally keeps your map in one browser. If you run the small mind map server on a computer on your home network, such as a Raspberry Pi, every phone, tablet and computer on that network can open and save the same maps.

The server is [`mindmap_server.py`](../../mindmap_server.py). It needs only Python 3, with nothing to install. It serves the editor and keeps your maps as `.zip` files in one folder. It also serves the [Diagram Editor](#diagrams), and keeps diagrams in a folder of their own.

**There is no password.** Anyone who can reach the server can read and change the maps, so run it only on a network you trust. To use it away from home, put the server and your devices on a private network such as [Tailscale](https://tailscale.com/) rather than opening it to the internet.

## Get the files

Clone the repository onto the computer that will run the server:

```
git clone https://github.com/romilly/browser-based-tools.git
cd browser-based-tools
```

The server needs `mindmap_server.py` and `mindmap-editor.html` side by side, as they are in the repository, with `diagram-editor.html` beside them for diagrams. It uses only Python's standard library, so there is nothing to install: you don't need a virtual environment or `pip`. (The packages in `requirements-dev.txt` are only for running the tests.)

## Run the server

In the repository folder, run [`start-mmserver.py`](../../start-mmserver.py):

```
python3 start-mmserver.py
```

It prints `Serving on port 8765: mind maps at /, diagrams at /diagram-editor.html; Ctrl+C to stop` and keeps running until you press Ctrl+C.

Then, on any device on the network, browse to `http://<server name or address>:8765/`, for example `http://raspberrypi.local:8765/`. The **File** menu now has **Open from server…** and **Save to server**.

### Changing the folder or port

The maps are kept in `~/mindmaps`, which is created if it doesn't exist. To change that, edit the `start_mind_map_server(...)` line in `start-mmserver.py`. It takes:

- the folder for the maps;
- `port=8765`, the port to listen on;
- `host='0.0.0.0'`, which accepts connections from the whole network. Use `'127.0.0.1'` for this computer only;
- `editor=`, the path of `mindmap-editor.html`, if it isn't beside `mindmap_server.py`;
- `diagrams=`, the folder for the diagrams. By default it is a `diagrams` folder inside the maps folder, made when the first diagram is saved;
- `diagram_editor=`, the path of `diagram-editor.html`, if it isn't beside `mindmap_server.py`.

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
  - On an Android phone or tablet, add `.local` to the server's name: `http://raspberrypi.local:8765/`, not `http://raspberrypi:8765/`. A name that works on your computers can fail on Android without it.
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

## Folders

Maps can be kept in folders on the server. **Open from server…** shows one folder at a time: choose a folder to look inside it, and use the path at the top of the list to go back up.

- **Save to server** asks where a new map goes. Walk to the folder, change the name if you like, and choose **Save here**. **New folder…** makes a folder to save into.
- **Move…** and **Delete** are beside each map in both **Open from server…** and **Save to server**, so you can tidy up while saving.
- **Move…** beside a map renames it or puts it in another folder: walk to the folder, change the name if you like, and choose **Move here**. **Move…** beside a folder does the same for the folder and everything in it. Afterwards you are back where you started, opening or saving; **Cancel** during a move takes you back too.
- **Delete** beside a map asks first, then moves the map to a `.trash` folder inside the maps folder, with the date and time added to its name. Nothing empties `.trash`, so to get a map back, move the file out of it and take the date out of its name; delete what you don't want from it yourself.

A folder is kept only while it has a map in it. A new folder appears on the server when you save or move a map into it, and a folder goes when its last map is moved out or deleted.

A map in a folder has the folders in its address, for example `http://raspberrypi.local:8765/?map=holidays/netherlands`. Moving or renaming a map, or a folder above it, changes that address, so links to it in your notes need changing too.

Folder and map names are lower-case letters, digits and underscores; the editor turns anything else you type into underscores. A folder of maps can't be called `diagrams` at the top level, because that is where the diagrams are kept.

The server must be new enough to know about folders. If the editor says the server is older than the editor, [restart it](#updating).

## Two devices, one map

Each save names the version it replaces. If someone saved the map on another device after you opened it, **Save to server** asks before replacing their version. It also asks before a new map replaces one of the same name already on the server.

## Diagrams

The same server serves the Diagram Editor at `http://<server name or address>:8765/diagram-editor.html`. Its **File** menu has **Open from server…** and **Save to server** too, and everything above works the same way for diagrams:

- Each diagram has its own address, with `?diagram=` and its name, for example `http://raspberrypi.local:8765/diagram-editor.html?diagram=order_handling`.
- **Ctrl+S** saves a diagram from the server back under the same name, even if you change its title.
- The browser asks before you leave with changes not saved to the server, and **Save to server** asks before replacing a version saved on another device.
- Diagrams have [folders](#folders), **Move…** and **Delete** in the same way, with their own `.trash` inside the diagrams folder.

Diagrams are kept as `.yaml` files in the `diagrams` folder inside the maps folder (`~/mindmaps/diagrams` unless you changed it). Maps and diagrams are listed separately, so a map and a diagram can have the same name.

## Backing up

The maps are ordinary `.zip` files in the server's folder (`~/mindmaps` unless you changed it), and the diagrams are `.yaml` files in its `diagrams` folder, so back up that folder; folders you make in the editor are ordinary folders inside it. Each file opens in its editor with **Open**, as well as from the server.

[Mind Map Editor](../index.md)
