/// Mobile File Indexer for Beru (Android/Flutter).
/// Scoped-storage file search returning up to 5 candidates with type hints and recency.

import 'dart:io';

class FileCandidate {
  final String path;
  final String name;
  final int size;
  final int modified;
  final String type;

  FileCandidate({
    required this.path,
    required this.name,
    required this.size,
    required this.modified,
    required this.type,
  });

  Map<String, dynamic> toJson() => {
        "path": path,
        "name": name,
        "size": size,
        "modified": modified,
        "type": type,
      };
}

class MobileFileIndex {
  final List<String> approvedFolders;

  MobileFileIndex({this.approvedFolders = const ["/storage/emulated/0/Download/Beru"]});

  /// Finds up to 5 matching file candidates within approved scoped storage directories
  Future<List<FileCandidate>> findFile(String query) async {
    final lowerQuery = query.toLowerCase().trim();
    final List<FileCandidate> candidates = [];

    // Filter type hints (e.g., 'pdf', 'photo', 'image', 'document')
    String? typeHint;
    if (lowerQuery.contains("pdf")) typeHint = ".pdf";
    if (lowerQuery.contains("photo") || lowerQuery.contains("image")) typeHint = ".jpg";

    for (final folderPath in approvedFolders) {
      final dir = Directory(folderPath);
      if (!dir.existsSync()) continue;

      final entities = dir.listSync();
      for (final entity in entities) {
        if (entity is File) {
          final fileName = entity.uri.pathSegments.last;
          final lowerName = fileName.toLowerCase();

          bool matches = lowerName.contains(lowerQuery);
          if (typeHint != null && lowerName.endsWith(typeHint)) {
            matches = true;
          }

          if (matches) {
            final stat = entity.statSync();
            candidates.add(FileCandidate(
              path: entity.path,
              name: fileName,
              size: stat.size,
              modified: stat.modified.millisecondsSinceEpoch,
              type: _deriveMime(fileName),
            ));
          }
        }
      }
    }

    // Sort by recency descending, limit to 5 candidates
    candidates.sort((a, b) => b.modified.compareTo(a.modified));
    return candidates.take(5).toList();
  }

  String _deriveMime(String filename) {
    if (filename.endsWith(".pdf")) return "application/pdf";
    if (filename.endsWith(".jpg") || filename.endsWith(".png")) return "image/jpeg";
    return "application/octet-stream";
  }
}
