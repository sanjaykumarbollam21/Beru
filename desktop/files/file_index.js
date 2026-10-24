/**
 * Desktop File Search Indexer for Electron / Node.js.
 * Searches user-approved folders and returns up to 5 matching candidates.
 */

const fs = require("fs");
const path = require("path");

class DesktopFileIndex {
  constructor(approvedFolders = []) {
    this.approvedFolders = approvedFolders.length > 0 ? approvedFolders : [
      path.join(process.env.USERPROFILE || process.env.HOME || ".", "Downloads"),
      path.join(process.env.USERPROFILE || process.env.HOME || ".", "Documents")
    ];
  }

  findFile(query) {
    const lowerQuery = query.toLowerCase().trim();
    const candidates = [];

    let typeHint = null;
    if (lowerQuery.includes("pdf")) typeHint = ".pdf";
    if (lowerQuery.includes("photo") || lowerQuery.includes("image")) typeHint = ".jpg";

    for (const folder of this.approvedFolders) {
      if (!fs.existsSync(folder)) continue;

      try {
        const files = fs.readdirSync(folder);
        for (const file of files) {
          const lowerName = file.toLowerCase();
          const filePath = path.join(folder, file);

          let matches = lowerName.includes(lowerQuery);
          if (typeHint && lowerName.endsWith(typeHint)) {
            matches = true;
          }

          if (matches) {
            try {
              const stat = fs.statSync(filePath);
              if (stat.isFile()) {
                candidates.push({
                  path: filePath,
                  name: file,
                  size: stat.size,
                  modified: stat.mtimeMs,
                  type: this._deriveMime(file)
                });
              }
            } catch (e) {
              // Ignore unreadable files
            }
          }
        }
      } catch (e) {
        // Ignore unreadable folders
      }
    }

    candidates.sort((a, b) => b.modified - a.modified);
    return candidates.slice(0, 5);
  }

  _deriveMime(filename) {
    if (filename.endsWith(".pdf")) return "application/pdf";
    if (filename.endsWith(".jpg") || filename.endsWith(".png")) return "image/jpeg";
    if (filename.endsWith(".zip")) return "application/zip";
    return "application/octet-stream";
  }
}

module.exports = DesktopFileIndex;
