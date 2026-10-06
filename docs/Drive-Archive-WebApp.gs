/**
 * Drive Archive Web App -- lets the pipeline save each issuance document into
 * YOUR Google Drive and get a link back for the briefing email.
 *
 * It runs as you, in your account: files use your own Drive storage, and no
 * IT, service account, or Shared Drive is involved. The pipeline POSTs the
 * document (with a secret token); this script files it as
 *
 *   Regulatory Archive/<REGULATOR>/<TYPE>/<REGULATOR_TYPE_NUMBER.ext>
 *
 * (creating folders as needed) and returns the file's link. If the same
 * filename already exists in that folder, it returns the existing link
 * instead of making a duplicate, so re-runs are safe.
 *
 * If this ever fails, the pipeline automatically falls back to attaching the
 * document to the email -- nothing is lost.
 *
 * SETUP (about 5 minutes, one time)
 * 1. In Google Drive, create ONE folder, e.g. "Regulatory Archive". Open it
 *    and copy the ID from the URL: drive.google.com/drive/folders/<THIS PART>
 *    Share this folder (Viewer) with the people who should open the links --
 *    the files are private to you otherwise.
 * 2. Go to script.google.com -> New project. Delete the starter code and
 *    paste this whole file in.
 * 3. Replace PASTE_FOLDER_ID_HERE with the folder ID, and replace
 *    PASTE_A_LONG_RANDOM_SECRET_HERE with a long random string (e.g. 40+
 *    random letters/numbers). Keep that string -- you'll paste the same one
 *    into GitHub.
 * 4. Click Run on "authorizeOnce". Approve the Drive permission (Advanced ->
 *    Go to project, if Google warns it's unverified -- normal for your own
 *    script).
 * 5. Deploy -> New deployment -> type "Web app".
 *      Execute as: Me
 *      Who has access: Anyone
 *    Click Deploy and copy the "Web app URL" (ends in /exec).
 *    ("Anyone" means anyone with the URL can reach it, but without the
 *    secret token every request is rejected and nothing is saved.)
 * 6. In GitHub -> Settings -> Secrets and variables -> Actions, add:
 *      DRIVE_UPLOAD_URL   = the Web app URL
 *      DRIVE_UPLOAD_TOKEN = the same secret string from step 3
 *
 * If you change the code later: Deploy -> Manage deployments -> edit -> New
 * version (the URL stays the same).
 */

const FOLDER_ID = 'PASTE_FOLDER_ID_HERE';
const SECRET_TOKEN = 'PASTE_A_LONG_RANDOM_SECRET_HERE';

function authorizeOnce() {
  // Run once from the editor so Google asks for Drive permission.
  DriveApp.getFolderById(FOLDER_ID).getName();
}

function getOrCreateSubfolder_(parent, name) {
  const existing = parent.getFoldersByName(name);
  return existing.hasNext() ? existing.next() : parent.createFolder(name);
}

// REGULATOR_TYPE_NUMBER.ext -> root/REGULATOR/TYPE, else root/Unsorted.
function targetFolderFor_(root, fileName) {
  const m = fileName.match(/^([A-Z]+)_([A-Z0-9-]+)_/);
  if (!m) return getOrCreateSubfolder_(root, 'Unsorted');
  return getOrCreateSubfolder_(getOrCreateSubfolder_(root, m[1]), m[2]);
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (!body.token || body.token !== SECRET_TOKEN) return json_({ ok: false, error: 'bad token' });
    if (!body.filename || !body.data) return json_({ ok: false, error: 'missing filename or data' });

    // Keep the name to safe characters; never trust a path from outside.
    const name = String(body.filename).replace(/[^A-Za-z0-9._-]/g, '-');
    const folder = targetFolderFor_(DriveApp.getFolderById(FOLDER_ID), name);

    const existing = folder.getFilesByName(name);
    if (existing.hasNext()) return json_({ ok: true, url: existing.next().getUrl(), duplicate: true });

    const blob = Utilities.newBlob(
      Utilities.base64Decode(body.data), body.content_type || 'application/octet-stream', name);
    const file = folder.createFile(blob);
    return json_({ ok: true, url: file.getUrl() });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}
