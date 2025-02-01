from twisted.mail import imap4
from twisted.internet import reactor, protocol, defer
import mailbox
import os
import configparser
from zope.interface import implementer

# Load authentication details from config file
CONFIG_FILE = "config.ini"
config = configparser.ConfigParser()
config.read(CONFIG_FILE)
USERNAME = config.get("AUTH", "username", fallback="user").encode("utf-8")
PASSWORD = config.get("AUTH", "password", fallback="password").encode("utf-8")

IMAP_PORT = int(config.get("SERVER", "port", fallback=1430))
IMAP_ADDRESS = config.get("SERVER", "address", fallback="127.0.0.1")

MBOX_DIR = "mailboxes"  # Directory storing all mbox files
os.makedirs(MBOX_DIR, exist_ok=True)

@implementer(imap4.IMailbox)
class IndexedMboxMailbox:
    """IMAP4 mailbox that supports indexing, searching, and message deletion."""

    def __init__(self, folder_name):
        self.folder_name = folder_name
        self.mbox_file = os.path.join(MBOX_DIR, f"{folder_name}.mbox")
        self.mbox = mailbox.mbox(self.mbox_file)
        self.listeners = []
        self._load_index()

    def _load_index(self):
        """Indexes the messages for faster access."""
        self.messages = list(self.mbox)
        self.index = {i + 1: msg for i, msg in enumerate(self.messages)}

    def getFlags(self):
        return defer.succeed([])

    def getHierarchicalDelimiter(self):
        return defer.succeed("/")

    def getMessageCount(self):
        return defer.succeed(len(self.messages))

    def getRecentCount(self):
        return defer.succeed(len(self.messages))

    def getUnseenCount(self):
        return defer.succeed(0)

    def isWriteable(self):
        return defer.succeed(True)

    def getUIDValidity(self):
        return defer.succeed(1)

    def fetch(self, messages, uid):
        """Fetch messages based on index."""
        msgs = [imap4.MessageSet(msg_id) for msg_id in messages if msg_id in self.index]
        return defer.succeed(msgs)

    def fetchMessage(self, message_id):
        """Fetch an individual message."""
        if message_id in self.index:
            return defer.succeed(self.index[message_id].as_string().encode("utf-8"))
        return defer.fail(imap4.MailboxException("Message not found"))

    def deleteMessage(self, message_id):
        """Delete a message from the mailbox."""
        if message_id in self.index:
            del self.mbox[message_id - 1]
            self.mbox.flush()
            self._load_index()
            return defer.succeed(True)
        return defer.fail(imap4.MailboxException("Message not found"))

    def search(self, query):
        """Search messages by subject or body."""
        results = []
        for msg_id, msg in self.index.items():
            if query.lower() in msg.get("subject", "").lower() or query.lower() in msg.get_payload(decode=True).decode(errors='ignore').lower():
                results.append(msg_id)
        return defer.succeed(results)

    def requestStatus(self, names):
        return defer.succeed({})

    def addListener(self, listener):
        self.listeners.append(listener)

    def removeListener(self, listener):
        self.listeners.remove(listener)

@implementer(imap4.IAccount)
class MboxUser:
    """Represents a user with multiple mailboxes."""
    def __init__(self):
        self.mailboxes = {"INBOX": IndexedMboxMailbox("INBOX")}

    def addMailbox(self, name, mbox):
        self.mailboxes[name] = mbox

    def select(self, name, rw=False):
        folder_name = name.decode("utf-8")
        if folder_name not in self.mailboxes:
            self.mailboxes[folder_name] = IndexedMboxMailbox(folder_name)
        return defer.succeed(self.mailboxes[folder_name])

    def listMailboxes(self, ref, wildcard):
        return defer.succeed(list(self.mailboxes.keys()))

    def create(self, path):
        self.mailboxes[path] = IndexedMboxMailbox(path)
        return defer.succeed(True)

    def delete(self, path):
        if path in self.mailboxes:
            del self.mailboxes[path]
            return defer.succeed(True)
        return defer.fail(imap4.MailboxException("Mailbox not found"))

class MboxIMAPServer(imap4.IMAP4Server):
    """IMAP4 server that serves multiple mbox folders."""

    def __init__(self, user):
        super().__init__()
        self.user = user

    def authenticateLogin(self, username, password):
        if username == USERNAME and password == PASSWORD:
            return defer.succeed(self.user)
        return defer.fail(imap4.error("Authentication failed"))

class MboxIMAPFactory(protocol.Factory):
    """Factory for creating IMAP connections."""

    def buildProtocol(self, addr):
        return MboxIMAPServer(MboxUser())

if __name__ == "__main__":
    reactor.listenTCP(IMAP_PORT, MboxIMAPFactory(), interface=IMAP_ADDRESS)
    print(f"IMAP server running on {IMAP_ADDRESS}:{IMAP_PORT}...")
    reactor.run()
