/**
 * Drive Attachment Copier (optional) -- files briefing-email attachments into
 * Google Drive automatically, one folder per regulator and one subfolder per
 * issuance type:
 *
 *   Regulatory Archive/
 *     BIR/  RMC/  RR/  RMO/
 *     IC/   CL/   ADVISORY/  MC/
 *     SEC/  MC/   RESOLUTION/  OPINION/  DECISION/
 *     Unsorted/   (anything whose filename doesn't match the standard)
 *
 * Attachment filenames follow the standard REGULATOR_TYPE_NUMBER.ext, e.g.
 * BIR_RMC_RMC-No-61-2026.pdf (set in core/archive.py). Folders are created
 * the first time they're needed.
 *
 * Runs in YOUR Google account (the mailbox that receives -- or sends -- the
 * "[Regulatory Briefing]" emails). No IT, no GitHub change, no service
 * account. Files use your own Drive storage.
 *
 * SETUP (about 3 minutes, one time)
 * 1. In Google Drive, create ONE folder, e.g. "Regulatory Archive". Open it
 *    and copy the ID from the URL: drive.google.com/drive/folders/<THIS PART>
 * 2. Go to script.google.com -> New project. Delete the starter code and
 *    paste this whole file in.
 * 3. Replace PASTE_FOLDER_ID_HERE below with the folder ID.
 * 4. Click Run on "copyBriefingAttachments". Google asks you to authorize
 *    (Gmail + Drive access to your own account) -- approve it.
 *    If you see "Google hasn't verified this app", click Advanced -> Go to
 *    project. That's normal for your own script.
 * 5. Click the clock icon (Triggers) -> Add Trigger -> function:
 *    copyBriefingAttachments, event source: Time-driven, Hour timer, Every hour.
 *
 * Each email is remembered by its Gmail message ID, and a file whose name
 * already exists in its folder is skipped, so nothing is copied twice. To
 * share the archive, share the root Drive folder the normal way.
 */

const FOLDER_ID = 'PASTE_FOLDER_ID_HERE';
const SEARCH = 'subject:"[Regulatory Briefing]" has:attachment newer_than:30d';
const PROP_KEY = 'processedMessageIds';
const MAX_REMEMBERED = 400; // plenty for 30 days; keeps storage tiny

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

function copyBriefingAttachments() {
  const props = PropertiesService.getScriptProperties();
  const done = JSON.parse(props.getProperty(PROP_KEY) || '[]');
  const doneSet = {};
  done.forEach(function (id) { doneSet[id] = true; });

  const root = DriveApp.getFolderById(FOLDER_ID);

  GmailApp.search(SEARCH, 0, 50).forEach(function (thread) {
    thread.getMessages().forEach(function (message) {
      const id = message.getId();
      if (doneSet[id]) return;
      if (message.getSubject().indexOf('[Regulatory Briefing]') !== 0) return;

      message.getAttachments({ includeInlineImages: false, includeAttachments: true })
        .forEach(function (att) {
          const name = att.getName();
          const folder = targetFolderFor_(root, name);
          if (folder.getFilesByName(name).hasNext()) return; // already filed
          folder.createFile(att.copyBlob().setName(name));
        });

      doneSet[id] = true;
      done.push(id);
    });
  });

  props.setProperty(PROP_KEY, JSON.stringify(done.slice(-MAX_REMEMBERED)));
}
