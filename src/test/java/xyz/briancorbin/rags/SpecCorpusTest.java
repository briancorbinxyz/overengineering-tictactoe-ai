package xyz.briancorbin.rags;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SpecCorpusTest {

  @Test
  void aTagCheckoutIsDetachedSoHeadIsTheCommit(@TempDir Path dir) throws Exception {
    Files.createDirectories(dir.resolve(".git"));
    Files.writeString(dir.resolve(".git/HEAD"), "c64d41c2e5d0d42c4fefd1b506cb083b9812bf6c\n");
    assertEquals("c64d41c2e5d0d42c4fefd1b506cb083b9812bf6c", SpecCorpus.commitOf(dir));
  }

  @Test
  void aBranchCheckoutIsResolvedThroughPackedRefs(@TempDir Path dir) throws Exception {
    Files.createDirectories(dir.resolve(".git"));
    Files.writeString(dir.resolve(".git/HEAD"), "ref: refs/heads/main\n");
    Files.writeString(
        dir.resolve(".git/packed-refs"),
        "# pack-refs with: peeled fully-peeled sorted\n0123456789abcdef0123456789abcdef01234567 refs/heads/main\n");
    assertEquals("0123456789abcdef0123456789abcdef01234567", SpecCorpus.commitOf(dir));
  }

  @Test
  void aWorktreeIsFollowedToItsGitDirectory(@TempDir Path dir) throws Exception {
    Path wt = Files.createDirectories(dir.resolve("main/.git/worktrees/pre28"));
    Files.writeString(wt.resolve("HEAD"), "c64d41c2e5d0d42c4fefd1b506cb083b9812bf6c\n");
    Path checkout = Files.createDirectories(dir.resolve("spectastic"));
    Files.writeString(checkout.resolve(".git"), "gitdir: " + wt + "\n");
    assertEquals("c64d41c2e5d0d42c4fefd1b506cb083b9812bf6c", SpecCorpus.commitOf(checkout));
  }

  @Test
  void theSpecIsTheFolderUnderSpecs() {
    assertEquals("059-corpus-retrieval-scale", SpecCorpus.specOf("specs/059-corpus-retrieval-scale/spec.html"));
    assertEquals(
        "094-visual-sidecar-convention",
        SpecCorpus.specOf("specs/094-visual-sidecar-convention/changes/withdrawn/2026-08-14-bind-the-checks/proposal.html"));
  }
}
