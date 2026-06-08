Build a Docker/OCI image for the current project using podman, run a local health-check test, and push to the private registry at 192.168.7.17:5000.

## How to determine configuration

**Image name:** Use the current project directory name (basename of the working directory) as the image name, converted to lowercase with spaces replaced by hyphens.

**Tag:** Use the argument provided by the user (e.g. `/container-deploy v1.2.0`). If no argument is given, use `latest`.

**Registry:** Always `192.168.7.17:5000` (plain HTTP, no authentication — LAN-only)

**App port:** Check the source code to determine what port the app listens on (look for `app.run`, `listen`, `EXPOSE` in Dockerfile if one exists, etc.). Default to `8080` if unclear. Use port `15000` on the host for the health-check test to avoid conflicts.

## Steps to follow

1. **Pre-flight check**
   - Verify a `Dockerfile` exists in the current directory. If not, tell the user and stop.
   - Confirm `podman` is available. If not, tell the user and stop.

2. **Build**
   - Run: `podman build --tls-verify=false -t 192.168.7.17:5000/<image-name>:<tag> .`
   - Show build output. Report success or failure. Stop if build fails.

3. **Local health-check test**
   - Start: `podman run --rm -d --name <image-name>-healthcheck -p 15000:<app-port> 192.168.7.17:5000/<image-name>:<tag>`
   - Wait 15 seconds for the app to start.
   - Test: `curl -sf --max-time 10 http://localhost:15000`
   - Stop the container: `podman stop <image-name>-healthcheck`
   - Report **PASSED** or **FAILED**. Stop if health-check fails.

4. **Push to registry**
   - The registry has no authentication, so no `podman login` is required.
   - Push: `podman push 192.168.7.17:5000/<image-name>:<tag> --tls-verify=false`

5. **Summary**
   - Report the full image reference that was pushed: `192.168.7.17:5000/<image-name>:<tag>`
   - Remind the user to use this image reference when deploying on TrueNAS Scale Custom App.
   - If any step failed, clearly state which step and the reason.
