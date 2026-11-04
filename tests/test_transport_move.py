def test_transport_protocol_lives_in_core_and_is_reexported_by_sim():
    from wpcap import transport as core
    from wpcap.sim import transport as sim

    assert sim.Transport is core.Transport
    assert hasattr(core, "Transport")
