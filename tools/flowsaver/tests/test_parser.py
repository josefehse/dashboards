"""Tests for the flow log parser and DuckDB loader."""

import json
from pathlib import Path

import pytest

from flowloganalysis.parser import parse_flow_tuple, parse_flowlog_file, parse_flowlog_json
from flowloganalysis.loader import open_db, load_records, get_row_count

SAMPLE_FILE = Path(__file__).resolve().parent.parent / "samples" / "VnetflowSample1.json"


class TestParseFlowTuple:
    def test_basic_tuple(self):
        raw = "1776124826940,10.0.2.4,168.61.215.74,123,123,17,O,C,NX,5,450,5,660"
        result = parse_flow_tuple(raw)
        assert result["src_ip"] == "10.0.2.4"
        assert result["dst_ip"] == "168.61.215.74"
        assert result["src_port"] == 123
        assert result["dst_port"] == 123
        assert result["protocol"] == "UDP"
        assert result["direction"] == "Outbound"
        assert result["state"] == "Continuing"
        assert result["encryption"] == "NX"
        assert result["packets_src_to_dst"] == 5
        assert result["bytes_src_to_dst"] == 450
        assert result["packets_dst_to_src"] == 5
        assert result["bytes_dst_to_src"] == 660
        assert result["timestamp_epoch_ms"] == 1776124826940

    def test_tcp_inbound_begin(self):
        raw = "1776124838681,20.116.42.129,10.0.2.4,41920,8443,6,I,B,NX,0,0,0,0"
        result = parse_flow_tuple(raw)
        assert result["protocol"] == "TCP"
        assert result["direction"] == "Inbound"
        assert result["state"] == "Begin"
        assert result["packets_src_to_dst"] == 0
        assert result["bytes_src_to_dst"] == 0

    def test_invalid_field_count(self):
        with pytest.raises(ValueError, match="Expected 13 fields"):
            parse_flow_tuple("1,2,3,4,5")

    def test_flow_time_conversion(self):
        raw = "1776124826940,10.0.2.4,168.61.215.74,123,123,17,O,C,NX,5,450,5,660"
        result = parse_flow_tuple(raw)
        assert result["flow_time"].year == 2026


class TestParseFlowlogFile:
    def test_sample_file_exists(self):
        assert SAMPLE_FILE.exists(), f"Sample file not found at {SAMPLE_FILE}"

    def test_parses_all_tuples(self):
        records = parse_flowlog_file(SAMPLE_FILE)
        assert len(records) == 3997, f"Expected 3997 records, got {len(records)}"

    def test_all_records_have_required_fields(self):
        records = parse_flowlog_file(SAMPLE_FILE)
        required = {"src_ip", "dst_ip", "src_port", "dst_port", "protocol",
                     "direction", "state", "flow_time", "rule_name"}
        for rec in records[:100]:  # spot-check first 100
            for field in required:
                assert field in rec, f"Missing field {field}"

    def test_protocols_are_mapped(self):
        records = parse_flowlog_file(SAMPLE_FILE)
        protocols = {r["protocol"] for r in records}
        assert protocols <= {"TCP", "UDP"}, f"Unexpected protocols: {protocols}"

    def test_directions_are_mapped(self):
        records = parse_flowlog_file(SAMPLE_FILE)
        directions = {r["direction"] for r in records}
        assert directions <= {"Inbound", "Outbound"}, f"Unexpected directions: {directions}"

    def test_states_are_mapped(self):
        records = parse_flowlog_file(SAMPLE_FILE)
        states = {r["state"] for r in records}
        assert states <= {"Begin", "Continuing", "End"}, f"Unexpected states: {states}"


class TestDuckDBLoader:
    def test_create_db_in_memory(self):
        conn = open_db()
        assert conn is not None
        conn.close()

    def test_load_and_count(self):
        records = parse_flowlog_file(SAMPLE_FILE)
        conn = open_db()
        loaded = load_records(conn, records)
        assert loaded == 3997
        assert get_row_count(conn) == 3997
        conn.close()

    def test_query_by_source_ip(self):
        records = parse_flowlog_file(SAMPLE_FILE)
        conn = open_db()
        load_records(conn, records)
        result = conn.execute(
            "SELECT COUNT(*) FROM flow_logs WHERE src_ip = '10.0.2.4'"
        ).fetchone()[0]
        assert result > 0
        conn.close()

    def test_query_aggregation(self):
        records = parse_flowlog_file(SAMPLE_FILE)
        conn = open_db()
        load_records(conn, records)
        result = conn.execute("""
            SELECT dst_ip, SUM(bytes_src_to_dst) as total_bytes
            FROM flow_logs
            WHERE dst_ip = '4.172.75.22'
            GROUP BY dst_ip
        """).fetchone()
        assert result is not None
        assert result[1] > 0, "Expected non-zero bytes"
        conn.close()

    def test_query_denied_flows(self):
        records = parse_flowlog_file(SAMPLE_FILE)
        conn = open_db()
        load_records(conn, records)
        result = conn.execute(
            "SELECT COUNT(*) FROM flow_logs WHERE state = 'Begin'"
        ).fetchone()[0]
        assert result > 0
        conn.close()

    def test_empty_records(self):
        conn = open_db()
        loaded = load_records(conn, [])
        assert loaded == 0
        assert get_row_count(conn) == 0
        conn.close()
