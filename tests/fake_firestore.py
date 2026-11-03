"""테스트용 가짜 Firestore. 실제 Firebase 에 접속하지 않고 storage.py 의 Firestore 코드를 검증한다.

storage.py 가 쓰는 기능만 흉내 낸다: collection/document/get/set(merge)/update/delete/stream,
where("==") 쿼리, 하위 컬렉션, batch, transaction, SERVER_TIMESTAMP, Increment.
"""
import copy
import datetime
import types
import uuid


class _ServerTimestamp:
    pass


class Increment:
    def __init__(self, value):
        self.value = value


def _transactional(fn):
    def run(transaction):
        return fn(transaction)
    return run


# storage.fb_firestore 대신 끼워 넣는 모듈
module = types.SimpleNamespace(SERVER_TIMESTAMP=_ServerTimestamp(), Increment=Increment, transactional=_transactional)


class FakeFirestore:
    def __init__(self):
        self.docs = {}  # (컬렉션, 문서, 하위 컬렉션, 문서, ...) -> dict

    def collection(self, name):
        return FakeCollection(self, (name,))

    def batch(self):
        return FakeBatch()

    def transaction(self):
        return FakeTransaction()

    def dump(self, collection):
        """최상위 컬렉션의 {문서 id: 데이터}. (검증용)"""
        return {p[1]: d for p, d in self.docs.items() if len(p) == 2 and p[0] == collection}


class FakeCollection:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def document(self, doc_id=None):
        return FakeDocRef(self.db, self.path + (doc_id or uuid.uuid4().hex[:20],))

    def where(self, field, op, value):
        return FakeQuery(self, [(field, op, value)])

    def stream(self):
        paths = sorted(p for p in self.db.docs if len(p) == len(self.path) + 1 and p[:-1] == self.path)
        return [FakeDocRef(self.db, p).get() for p in paths]


class FakeQuery:
    def __init__(self, collection, filters):
        self.collection, self.filters = collection, filters

    def where(self, field, op, value):
        return FakeQuery(self.collection, self.filters + [(field, op, value)])

    def stream(self):
        for _, op, _ in self.filters:
            assert op == "==", "가짜 Firestore 는 == 쿼리만 지원한다"
        return [s for s in self.collection.stream()
                if all(s.to_dict().get(f) == v for f, _, v in self.filters)]


class FakeDocRef:
    def __init__(self, db, path):
        self.db, self.path = db, path

    @property
    def id(self):
        return self.path[-1]

    def get(self, transaction=None):
        return FakeSnapshot(self, self.db.docs.get(self.path))

    def set(self, data, merge=False):
        old = self.db.docs.get(self.path, {}) if merge else {}
        new = dict(old)
        for k, v in data.items():
            if isinstance(v, _ServerTimestamp):
                v = datetime.datetime.now(datetime.timezone.utc)
            elif isinstance(v, Increment):
                v = old.get(k, 0) + v.value
            new[k] = v
        self.db.docs[self.path] = new

    def update(self, data):
        if self.path not in self.db.docs:
            raise KeyError(f"문서가 없습니다: {'/'.join(self.path)}")
        self.set(data, merge=True)

    def delete(self):
        self.db.docs.pop(self.path, None)

    def collection(self, name):
        return FakeCollection(self.db, self.path + (name,))


class FakeSnapshot:
    def __init__(self, ref, data):
        self.reference, self._data = ref, data

    @property
    def id(self):
        return self.reference.id

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return copy.deepcopy(self._data)


class FakeBatch:
    def __init__(self):
        self.ops = []

    def set(self, ref, data, merge=False):
        self.ops.append((ref, data, merge))

    def commit(self):
        for ref, data, merge in self.ops:
            ref.set(data, merge=merge)


class FakeTransaction:
    def set(self, ref, data, merge=False):
        ref.set(data, merge=merge)
