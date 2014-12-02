"""Tests for go.components.message_store_migrators."""

from twisted.internet.defer import inlineCallbacks

from vumi.tests.helpers import (
    VumiTestCase, MessageHelper, PersistenceHelper, import_skip)

try:
    from vumi.components.tests.message_store_old_models import (
        OutboundMessageVNone, InboundMessageVNone, BatchVNone,
        OutboundMessageV1, InboundMessageV1, OutboundMessageV2,
        InboundMessageV2)
    from vumi.components.message_store import (
        OutboundMessage as OutboundMessageV3,
        InboundMessage as InboundMessageV3)
    riak_import_error = None
except ImportError, e:
    riak_import_error = e


def bwt_value(batch_id, msg):
    return "%s$%s" % (batch_id, msg['timestamp'])


def bwa_in_value(batch_id, msg):
    return "%s$%s$%s" % (batch_id, msg['timestamp'], msg['from_addr'])


def bwa_out_value(batch_id, msg):
    return "%s$%s$%s" % (batch_id, msg['timestamp'], msg['to_addr'])


def batch_index(value):
    return ("batches_bin", value)


def bwt_index(value):
    return ("batches_with_timestamps_bin", value)


def bwa_index(value):
    return ("batches_with_addresses_bin", value)


class TestMigratorBase(VumiTestCase):
    def setUp(self):
        self.persistence_helper = self.add_helper(
            PersistenceHelper(use_riak=True))
        if riak_import_error is not None:
            import_skip(riak_import_error, 'riak')
        self.manager = self.persistence_helper.get_riak_manager()
        self.msg_helper = self.add_helper(MessageHelper())


class TestOutboundMessageMigrator(TestMigratorBase):
    @inlineCallbacks
    def setUp(self):
        yield super(TestOutboundMessageMigrator, self).setUp()
        self.outbound_vnone = self.manager.proxy(OutboundMessageVNone)
        self.outbound_v1 = self.manager.proxy(OutboundMessageV1)
        self.outbound_v2 = self.manager.proxy(OutboundMessageV2)
        self.outbound_v3 = self.manager.proxy(OutboundMessageV3)
        self.batch_vnone = self.manager.proxy(BatchVNone)

    @inlineCallbacks
    def test_migrate_vnone_to_v1(self):
        msg = self.msg_helper.make_outbound("outbound")
        old_batch = self.batch_vnone(key=u"batch-1")
        old_record = self.outbound_vnone(
            msg["message_id"], msg=msg, batch=old_batch)
        yield old_record.save()
        new_record = yield self.outbound_v1.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [old_batch.key])

    @inlineCallbacks
    def test_migrate_vnone_to_v1_without_batch(self):
        msg = self.msg_helper.make_outbound("outbound")
        old_record = self.outbound_vnone(
            msg["message_id"], msg=msg, batch=None)
        yield old_record.save()
        new_record = yield self.outbound_v1.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [])

    @inlineCallbacks
    def test_migrate_v1_to_v2_no_batches(self):
        msg = self.msg_helper.make_outbound("outbound")
        old_record = self.outbound_v1(msg["message_id"], msg=msg)
        yield old_record.save()
        new_record = yield self.outbound_v2.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [])

        # The migration doesn't set the new fields and indexes, that only
        # happens at save time.
        self.assertEqual(set(new_record.batches_with_timestamps), set([]))
        self.assertEqual(new_record._riak_object.get_indexes(), set([]))

        yield new_record.save()
        self.assertEqual(set(new_record.batches_with_timestamps), set([]))
        self.assertEqual(new_record._riak_object.get_indexes(), set([]))

    @inlineCallbacks
    def test_migrate_v1_to_v2_one_batch(self):
        msg = self.msg_helper.make_outbound("outbound")
        old_batch = self.batch_vnone(key=u"batch-1")
        old_record = self.outbound_v1(msg["message_id"], msg=msg)
        old_record.batches.add_key(old_batch.key)
        yield old_record.save()
        new_record = yield self.outbound_v2.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [old_batch.key])

        # The migration doesn't set the new fields and indexes, that only
        # happens at save time.

        self.assertEqual(set(new_record.batches_with_timestamps), set([]))
        self.assertEqual(
            new_record._riak_object.get_indexes(),
            set([batch_index("batch-1")]))

        yield new_record.save()
        self.assertEqual(
            set(new_record.batches_with_timestamps),
            set([bwt_value("batch-1", msg)]))
        self.assertEqual(new_record._riak_object.get_indexes(), set(
            [batch_index("batch-1"), bwt_index(bwt_value("batch-1", msg))]))

    @inlineCallbacks
    def test_migrate_v1_to_v2_two_batches(self):
        msg = self.msg_helper.make_outbound("outbound")
        batch_1 = self.batch_vnone(key=u"batch-1")
        batch_2 = self.batch_vnone(key=u"batch-2")
        old_record = self.outbound_v1(msg["message_id"], msg=msg)
        old_record.batches.add_key(batch_1.key)
        old_record.batches.add_key(batch_2.key)
        yield old_record.save()
        new_record = yield self.outbound_v2.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [batch_1.key, batch_2.key])

        # The migration doesn't set the new fields and indexes, that only
        # happens at save time.
        self.assertEqual(new_record._riak_object.get_indexes(), set([
            batch_index("batch-1"), batch_index("batch-2")]))

        yield new_record.save()
        self.assertEqual(new_record._riak_object.get_indexes(), set([
            batch_index("batch-1"),
            batch_index("batch-2"),
            bwt_index(bwt_value("batch-1", msg)),
            bwt_index(bwt_value("batch-2", msg)),
        ]))

    @inlineCallbacks
    def test_migrate_v2_to_v3_no_batches(self):
        msg = self.msg_helper.make_outbound("outbound")
        old_record = self.outbound_v2(msg["message_id"], msg=msg)
        yield old_record.save()
        new_record = yield self.outbound_v3.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [])

        # The migration doesn't set the new fields and indexes, that only
        # happens at save time.
        self.assertEqual(set(new_record.batches_with_timestamps), set([]))
        self.assertEqual(set(new_record.batches_with_addresses), set([]))
        self.assertEqual(new_record._riak_object.get_indexes(), set([]))

        yield new_record.save()
        self.assertEqual(set(new_record.batches_with_timestamps), set([]))
        self.assertEqual(set(new_record.batches_with_addresses), set([]))
        self.assertEqual(new_record._riak_object.get_indexes(), set([]))

    @inlineCallbacks
    def test_migrate_v2_to_v3_one_batch(self):
        msg = self.msg_helper.make_outbound("outbound")
        old_batch = self.batch_vnone(key=u"batch-1")
        old_record = self.outbound_v2(msg["message_id"], msg=msg)
        old_record.batches.add_key(old_batch.key)
        yield old_record.save()
        new_record = yield self.outbound_v3.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [old_batch.key])

        # The migration doesn't set the new fields and indexes, that only
        # happens at save time.

        self.assertEqual(set(new_record.batches_with_addresses), set([]))
        self.assertEqual(new_record._riak_object.get_indexes(), set([
            batch_index("batch-1"),
            bwt_index(bwt_value("batch-1", msg)),
        ]))

        yield new_record.save()
        self.assertEqual(
            set(new_record.batches_with_timestamps),
            set([bwt_value("batch-1", msg)]))
        self.assertEqual(
            set(new_record.batches_with_addresses),
            set([bwa_out_value("batch-1", msg)]))
        self.assertEqual(new_record._riak_object.get_indexes(), set([
            batch_index("batch-1"),
            bwt_index(bwt_value("batch-1", msg)),
            bwa_index(bwa_out_value("batch-1", msg)),
        ]))

    @inlineCallbacks
    def test_migrate_v2_to_v3_two_batches(self):
        msg = self.msg_helper.make_outbound("outbound")
        batch_1 = self.batch_vnone(key=u"batch-1")
        batch_2 = self.batch_vnone(key=u"batch-2")
        old_record = self.outbound_v2(msg["message_id"], msg=msg)
        old_record.batches.add_key(batch_1.key)
        old_record.batches.add_key(batch_2.key)
        yield old_record.save()
        new_record = yield self.outbound_v3.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [batch_1.key, batch_2.key])

        # The migration doesn't set the new fields and indexes, that only
        # happens at save time.
        self.assertEqual(new_record._riak_object.get_indexes(), set([
            batch_index("batch-1"),
            batch_index("batch-2"),
            bwt_index(bwt_value("batch-1", msg)),
            bwt_index(bwt_value("batch-2", msg)),
        ]))

        yield new_record.save()
        self.assertEqual(new_record._riak_object.get_indexes(), set([
            batch_index("batch-1"),
            batch_index("batch-2"),
            bwt_index(bwt_value("batch-1", msg)),
            bwt_index(bwt_value("batch-2", msg)),
            bwa_index(bwa_out_value("batch-1", msg)),
            bwa_index(bwa_out_value("batch-2", msg)),
        ]))


class TestInboundMessageMigrator(TestMigratorBase):

    @inlineCallbacks
    def setUp(self):
        yield super(TestInboundMessageMigrator, self).setUp()
        self.inbound_vnone = self.manager.proxy(InboundMessageVNone)
        self.inbound_v1 = self.manager.proxy(InboundMessageV1)
        self.inbound_v2 = self.manager.proxy(InboundMessageV2)
        self.inbound_v3 = self.manager.proxy(InboundMessageV3)
        self.batch_vnone = self.manager.proxy(BatchVNone)

    @inlineCallbacks
    def test_migrate_vnone_to_v1(self):
        msg = self.msg_helper.make_inbound("inbound")
        old_batch = self.batch_vnone(key=u"batch-1")
        old_record = self.inbound_vnone(
            msg["message_id"], msg=msg, batch=old_batch)
        yield old_record.save()
        new_record = yield self.inbound_v1.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [old_batch.key])

    @inlineCallbacks
    def test_migrate_vnone_to_v1_without_batch(self):
        msg = self.msg_helper.make_inbound("inbound")
        old_record = self.inbound_vnone(
            msg["message_id"], msg=msg, batch=None)
        yield old_record.save()
        new_record = yield self.inbound_v1.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [])

    @inlineCallbacks
    def test_migrate_v1_to_v2_no_batches(self):
        msg = self.msg_helper.make_inbound("inbound")
        old_record = self.inbound_v1(msg["message_id"], msg=msg)
        yield old_record.save()
        new_record = yield self.inbound_v2.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [])

        # The migration doesn't set the new fields and indexes, that only
        # happens at save time.
        self.assertEqual(set(new_record.batches_with_timestamps), set([]))
        self.assertEqual(new_record._riak_object.get_indexes(), set([]))

        yield new_record.save()
        self.assertEqual(set(new_record.batches_with_timestamps), set([]))
        self.assertEqual(new_record._riak_object.get_indexes(), set([]))

    @inlineCallbacks
    def test_migrate_v1_to_v2_one_batch(self):
        msg = self.msg_helper.make_inbound("inbound")
        old_batch = self.batch_vnone(key=u"batch-1")
        old_record = self.inbound_v1(msg["message_id"], msg=msg)
        old_record.batches.add_key(old_batch.key)
        yield old_record.save()
        new_record = yield self.inbound_v2.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [old_batch.key])

        # The migration doesn't set the new fields and indexes, that only
        # happens at save time.

        self.assertEqual(set(new_record.batches_with_timestamps), set([]))
        self.assertEqual(
            new_record._riak_object.get_indexes(),
            set([batch_index("batch-1")]))

        yield new_record.save()
        self.assertEqual(
            set(new_record.batches_with_timestamps),
            set([bwt_value("batch-1", msg)]))
        self.assertEqual(new_record._riak_object.get_indexes(), set(
            [batch_index("batch-1"), bwt_index(bwt_value("batch-1", msg))]))

    @inlineCallbacks
    def test_migrate_v1_to_v2_two_batches(self):
        msg = self.msg_helper.make_inbound("inbound")
        batch_1 = self.batch_vnone(key=u"batch-1")
        batch_2 = self.batch_vnone(key=u"batch-2")
        old_record = self.inbound_v1(msg["message_id"], msg=msg)
        old_record.batches.add_key(batch_1.key)
        old_record.batches.add_key(batch_2.key)
        yield old_record.save()
        new_record = yield self.inbound_v2.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [batch_1.key, batch_2.key])

        # The migration doesn't set the new fields and indexes, that only
        # happens at save time.
        self.assertEqual(new_record._riak_object.get_indexes(), set([
            batch_index("batch-1"), batch_index("batch-2")]))

        yield new_record.save()
        self.assertEqual(new_record._riak_object.get_indexes(), set([
            batch_index("batch-1"),
            batch_index("batch-2"),
            bwt_index(bwt_value("batch-1", msg)),
            bwt_index(bwt_value("batch-2", msg)),
        ]))

    @inlineCallbacks
    def test_migrate_v2_to_v3_no_batches(self):
        msg = self.msg_helper.make_inbound("inbound")
        old_record = self.inbound_v2(msg["message_id"], msg=msg)
        yield old_record.save()
        new_record = yield self.inbound_v3.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [])

        # The migration doesn't set the new fields and indexes, that only
        # happens at save time.
        self.assertEqual(set(new_record.batches_with_timestamps), set([]))
        self.assertEqual(set(new_record.batches_with_addresses), set([]))
        self.assertEqual(new_record._riak_object.get_indexes(), set([]))

        yield new_record.save()
        self.assertEqual(set(new_record.batches_with_timestamps), set([]))
        self.assertEqual(set(new_record.batches_with_addresses), set([]))
        self.assertEqual(new_record._riak_object.get_indexes(), set([]))

    @inlineCallbacks
    def test_migrate_v2_to_v3_one_batch(self):
        msg = self.msg_helper.make_inbound("inbound")
        old_batch = self.batch_vnone(key=u"batch-1")
        old_record = self.inbound_v2(msg["message_id"], msg=msg)
        old_record.batches.add_key(old_batch.key)
        yield old_record.save()
        new_record = yield self.inbound_v3.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [old_batch.key])

        # The migration doesn't set the new fields and indexes, that only
        # happens at save time.

        self.assertEqual(set(new_record.batches_with_addresses), set([]))
        self.assertEqual(new_record._riak_object.get_indexes(), set([
            batch_index("batch-1"),
            bwt_index(bwt_value("batch-1", msg)),
        ]))

        yield new_record.save()
        self.assertEqual(
            set(new_record.batches_with_timestamps),
            set([bwt_value("batch-1", msg)]))
        self.assertEqual(
            set(new_record.batches_with_addresses),
            set([bwa_in_value("batch-1", msg)]))
        self.assertEqual(new_record._riak_object.get_indexes(), set([
            batch_index("batch-1"),
            bwt_index(bwt_value("batch-1", msg)),
            bwa_index(bwa_in_value("batch-1", msg)),
        ]))

    @inlineCallbacks
    def test_migrate_v2_to_v3_two_batches(self):
        msg = self.msg_helper.make_inbound("inbound")
        batch_1 = self.batch_vnone(key=u"batch-1")
        batch_2 = self.batch_vnone(key=u"batch-2")
        old_record = self.inbound_v2(msg["message_id"], msg=msg)
        old_record.batches.add_key(batch_1.key)
        old_record.batches.add_key(batch_2.key)
        yield old_record.save()
        new_record = yield self.inbound_v3.load(old_record.key)
        self.assertEqual(new_record.msg, msg)
        self.assertEqual(new_record.batches.keys(), [batch_1.key, batch_2.key])

        # The migration doesn't set the new fields and indexes, that only
        # happens at save time.
        self.assertEqual(new_record._riak_object.get_indexes(), set([
            batch_index("batch-1"),
            batch_index("batch-2"),
            bwt_index(bwt_value("batch-1", msg)),
            bwt_index(bwt_value("batch-2", msg)),
        ]))

        yield new_record.save()
        self.assertEqual(new_record._riak_object.get_indexes(), set([
            batch_index("batch-1"),
            batch_index("batch-2"),
            bwt_index(bwt_value("batch-1", msg)),
            bwt_index(bwt_value("batch-2", msg)),
            bwa_index(bwa_in_value("batch-1", msg)),
            bwa_index(bwa_in_value("batch-2", msg)),
        ]))
