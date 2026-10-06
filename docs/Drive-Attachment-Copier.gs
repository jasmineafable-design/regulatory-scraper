/**
 * Drive Attachment Copier (optional) -- copies briefing-email attachments
 * into a Google Drive folder, automatically.
 *
 * Runs in YOUR Google account (the mailbox that receives -- or sends -- the
 * "[Regulatory Briefing]" emails). No IT, no GitHub change, no service
 * account. Files use your own Drive storage.
 *
 * SETUP (about 3 minutes, one time)
 * 1. In Google Drive, create a folder, e.g. "Regulatory Archive". Open it and
 *    copy the ID from the URL: drive.google.com/drive/folders/<THIS PART>
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
 * It only touches emails with subject starting "[Regulatory Briefing]" that
 * have attachments. Each email is remembered by its Gmail message ID, so
 * nothing is copied twice -- even though Gmail groups briefings with the same
 * subject into one conversation. To share the archive, share the Drive folder
 * the normal way.
 */

const FOLDER_ID = 'PASTE_FOLDER_ID_HERE';
const SEARCH = 'subject:"[Regulatory Briefing]" has:attachment newer_than:30d';
const PROP_KEY = 'processedMessageIds';
const MAX_REMEMBERED = 400; // plenty for 30 days; keeps storage tiny

function copyBriefingAttachments() {
  const props = PropertiesService.getScriptProperties();
  const done = JSON.parse(props.getProperty(PROP_KEY) || '[]');
  const doneSet = {};
  done.forEach(function (id) { doneSet[id] = true; });

  const folder = DriveApp.getFolderById(FOLDER_ID);

  GmailApp.search(SEARCH, 0, 50).forEach(function (thread) {
    thread.getMessages().forEach(function (message) {
      const id = message.getId();
      if (doneSet[id]) return;
      if (message.getSubject().indexOf('[Regulatory Briefing]') !== 0) return;

      const stamp = Utilities.formatDate(message.getDate(), Session.getScriptTimeZone(), 'yyyy-MM-dd_HHmm');
      message.getAttachments({ includeInlineImages: false, includeAttachments: true })
        .forEach(function (att) {
          // Prefix with the email's date so same-named files never collide.
          folder.createFile(att.copyBlob().setName(stamp + '_' + att.getName()));
        });

      doneSet[id] = true;
      done.push(id);
    });
  });

  props.setProperty(PROP_KEY, JSON.stringify(done.slice(-MAX_REMEMBERED)));
}
