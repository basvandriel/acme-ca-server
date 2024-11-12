# import acme_ca_server


def test_is_package():
    # This will throw an import error if not found
    import acme_ca_server

    assert acme_ca_server
